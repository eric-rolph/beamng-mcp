-- BeamNG MCP GELua bridge.
--
-- This extension deliberately exposes a small, typed command surface. It does
-- not run client-provided Lua or accept arbitrary object fields/classes.

local M = {}

M.dependencies = {"core_gamestate"}

local LOG_TAG = "beamng_mcp_bridge"
local BRIDGE_VERSION = "0.3.0"
local SCHEMA_VERSION = 1
local LOOPBACK_ADDRESS = "127.0.0.1"
local WEBSOCKET_PATH = ""
local WEBSOCKET_PROTOCOL = "beamng-mcp-v1"
local CONFIG_PATH = "/settings/beamng_mcp.json"
local CONFIG_MARKER = "beamng-mcp-bridge"
local TOKEN_PLACEHOLDER = "__BEAMNG_MCP_TOKEN__"

local HARD_MAX_PAYLOAD_BYTES = 1048576
local MAX_EVENTS_PER_UPDATE = 64
local MAX_DATA_BYTES_PER_UPDATE = HARD_MAX_PAYLOAD_BYTES * 4
local MAX_OBJECT_RESULTS = 200
local MAX_IDENTIFIER_LENGTH = 96
local MAX_MANAGED_TRIGGERS_PER_PEER = 32
local MAX_MANAGED_TRIGGERS_TOTAL = 64
local MAX_TRIGGER_RESULTS = 100
local MAX_TRIGGER_EVENTS_PER_SECOND = 20
local TRIGGER_POSITION_ABSOLUTE_TOLERANCE = 0.0001
local TRIGGER_SCALE_ABSOLUTE_TOLERANCE = 0.000001
local TRIGGER_VECTOR_RELATIVE_TOLERANCE = 0.0000001
local TRIGGER_ROTATION_ABSOLUTE_TOLERANCE = 0.00001

local wsUtils = require("utils/wsUtils")

local server = nil
local config = nil
local peers = {}
local managedObjects = {}
local managedTriggers = {}
local managedTriggerNames = {}
local managedTriggerIds = {}
local triggerGeneration = 0
local elapsedSeconds = 0
local realElapsedSeconds = 0
local telemetryElapsed = 0
local heartbeatElapsed = 0
local pendingReload = nil
local safetyLease = nil
local restartServerRequested = false

local DEFAULT_CONFIG = {
  marker = CONFIG_MARKER,
  port = 8765,
  token = TOKEN_PLACEHOLDER,
  max_payload_bytes = 1048576,
  telemetry_interval_seconds = 0.5,
  heartbeat_interval_seconds = 5.0,
  heartbeat_timeout_seconds = 20.0,
  safety_lease_seconds = 1.0,
  safety_startup_grace_seconds = 5.0,
  allow_persistent_map_edits = false,
  allow_existing_map_object_edits = false
}

local REQUEST_KEYS = {
  schema = true,
  id = true,
  type = true,
  method = true,
  params = true,
  token = true
}

local CREATABLE_CLASSES = {
  TSStatic = true,
  PointLight = true,
  SpotLight = true,
  BeamNGWaypoint = true
}

local READ_ONLY_CLASSES = {
  BeamNGTrigger = true,
  ParticleEmitterNode = true
}

local COLLISION_TYPES = {
  ["Collision Mesh"] = true,
  ["Visible Mesh"] = true,
  ["None"] = true
}

local DECAL_TYPES = {
  ["Collision Mesh"] = true,
  ["Visible Mesh"] = true,
  ["None"] = true
}

local FIELD_RULES = {
  TSStatic = {
    shapeName = {kind = "asset_path"},
    collisionType = {kind = "enum", values = COLLISION_TYPES},
    decalType = {kind = "enum", values = DECAL_TYPES},
    annotation = {kind = "identifier"}
  },
  PointLight = {
    color = {kind = "color"},
    brightness = {kind = "number", min = 0, max = 100},
    range = {kind = "number", min = 0.1, max = 10000},
    castShadows = {kind = "boolean"},
    enabled = {kind = "boolean"}
  },
  SpotLight = {
    color = {kind = "color"},
    brightness = {kind = "number", min = 0, max = 100},
    range = {kind = "number", min = 0.1, max = 10000},
    innerAngle = {kind = "number", min = 0, max = 179},
    outerAngle = {kind = "number", min = 0.1, max = 179},
    castShadows = {kind = "boolean"},
    enabled = {kind = "boolean"}
  },
  BeamNGWaypoint = {
    radius = {kind = "number", min = 0.1, max = 1000}
  }
}

local READ_ONLY_FIELD_RULES = {
  BeamNGTrigger = {
    triggerMode = true,
    triggerTestType = true
  },
  ParticleEmitterNode = {
    dataBlock = true,
    emitter = true
  }
}

local RELOADABLE_EXTENSIONS = {
  ["beamng_mcp/bridge"] = "beamng__mcp_bridge"
}

local function shallowCopy(source)
  local result = {}
  for key, value in pairs(source or {}) do
    result[key] = value
  end
  return result
end

local function isFiniteNumber(value)
  return type(value) == "number"
    and value == value
    and value > -math.huge
    and value < math.huge
end

local function isInteger(value)
  return isFiniteNumber(value) and value == math.floor(value)
end

local function clamp(value, minimum, maximum)
  if value < minimum then return minimum end
  if value > maximum then return maximum end
  return value
end

local function validIdentifier(value)
  if type(value) ~= "string" or #value < 1 or #value > MAX_IDENTIFIER_LENGTH then
    return false
  end
  return value:match("^[%a_][%w_%-%.]*$") ~= nil
end

local function validRequestId(value)
  if type(value) ~= "string" or #value < 1 or #value > MAX_IDENTIFIER_LENGTH then
    return false
  end
  return value:match("^[%w][%w_%-%.:]*$") ~= nil
end

local function constantTimeEquals(left, right)
  if type(left) ~= "string" or type(right) ~= "string" or #left ~= #right then
    return false
  end

  local difference = 0
  for index = 1, #left do
    difference = difference + math.abs(string.byte(left, index) - string.byte(right, index))
  end
  return difference == 0
end

local function protocolError(code, message, details)
  return {
    code = code,
    message = message,
    details = details or {}
  }
end

local function pendingReloadMutationError()
  if not pendingReload then return nil end
  return protocolError(
    "extension_reload_pending",
    "scene mutations are unavailable while bridge extension reload is pending"
  )
end

local function responseEnvelope(request, result, requestError)
  local envelope = {
    schema = SCHEMA_VERSION,
    id = request and request.id or "protocol-error",
    type = "response",
    method = request and request.method or "protocol.error",
    params = {},
    token = nil
  }
  if requestError then
    envelope.error = requestError
  else
    envelope.result = result or {}
  end
  return envelope
end

local function eventEnvelope(method, params)
  return {
    schema = SCHEMA_VERSION,
    id = "event-" .. method,
    type = "event",
    method = method,
    params = params or {},
    token = nil
  }
end

local function encodeEnvelope(envelope)
  local ok, encoded = pcall(jsonEncode, envelope)
  if not ok or type(encoded) ~= "string" then
    log("E", LOG_TAG, "Unable to encode a protocol envelope")
    return nil
  end
  if config and #encoded > config.max_payload_bytes then
    log("E", LOG_TAG, "Refusing to send an oversized protocol envelope")
    return nil
  end
  return encoded
end

local function sendEnvelope(peerId, envelope)
  if not server then return false end
  local encoded = encodeEnvelope(envelope)
  if not encoded then return false end
  local ok = pcall(function() server:sendData(peerId, encoded) end)
  return ok
end

local function sendError(peerId, request, code, message, details)
  return sendEnvelope(
    peerId,
    responseEnvelope(request, nil, protocolError(code, message, details))
  )
end

local function authenticatedPeersCount()
  local count = 0
  for _, peer in pairs(peers) do
    if peer.authenticated then count = count + 1 end
  end
  return count
end

local function broadcastAuthenticated(envelope)
  for peerId, peer in pairs(peers) do
    if peer.authenticated then
      sendEnvelope(peerId, envelope)
    end
  end
end

local function readConfig()
  local loaded = nil
  local ok, result = pcall(jsonReadFile, CONFIG_PATH)
  if ok and type(result) == "table" then
    loaded = result
  end

  local resolved = shallowCopy(DEFAULT_CONFIG)
  for key, value in pairs(loaded or {}) do
    if DEFAULT_CONFIG[key] == nil then
      return nil, "unsupported configuration key: " .. tostring(key)
    end
    resolved[key] = value
  end

  if resolved.marker ~= CONFIG_MARKER then
    return nil, "configuration marker is invalid"
  end
  if not isInteger(resolved.port) or resolved.port < 1024 or resolved.port > 65535 then
    return nil, "port must be an integer from 1024 through 65535"
  end
  if type(resolved.token) ~= "string"
    or #resolved.token < 16
    or resolved.token == TOKEN_PLACEHOLDER then
    return nil, "replace the token placeholder with a secret of at least 16 characters"
  end
  if not isInteger(resolved.max_payload_bytes) then
    return nil, "max_payload_bytes must be an integer"
  end
  resolved.max_payload_bytes = clamp(resolved.max_payload_bytes, 4096, HARD_MAX_PAYLOAD_BYTES)

  if not isFiniteNumber(resolved.telemetry_interval_seconds) then
    return nil, "telemetry_interval_seconds must be numeric"
  end
  resolved.telemetry_interval_seconds = clamp(resolved.telemetry_interval_seconds, 0.2, 10)

  if not isFiniteNumber(resolved.heartbeat_interval_seconds) then
    return nil, "heartbeat_interval_seconds must be numeric"
  end
  resolved.heartbeat_interval_seconds = clamp(resolved.heartbeat_interval_seconds, 1, 30)

  if not isFiniteNumber(resolved.heartbeat_timeout_seconds) then
    return nil, "heartbeat_timeout_seconds must be numeric"
  end
  resolved.heartbeat_timeout_seconds = clamp(
    resolved.heartbeat_timeout_seconds,
    resolved.heartbeat_interval_seconds * 2,
    120
  )
  if not isFiniteNumber(resolved.safety_lease_seconds)
    or resolved.safety_lease_seconds < 0.25
    or resolved.safety_lease_seconds > 5 then
    return nil, "safety_lease_seconds must be from 0.25 through 5"
  end
  if not isFiniteNumber(resolved.safety_startup_grace_seconds)
    or resolved.safety_startup_grace_seconds < 0.25
    or resolved.safety_startup_grace_seconds > 5 then
    return nil, "safety_startup_grace_seconds must be from 0.25 through 5"
  end
  resolved.allow_persistent_map_edits = resolved.allow_persistent_map_edits == true
  resolved.allow_existing_map_object_edits = resolved.allow_existing_map_object_edits == true
  return resolved, nil
end

local function tableComponent(value, arrayIndex, key)
  if type(value) ~= "table" then return nil end
  if value[arrayIndex] ~= nil then return value[arrayIndex] end
  return value[key]
end

local function parseVector3(value, label, minimum, maximum, positiveOnly)
  local x = tableComponent(value, 1, "x")
  local y = tableComponent(value, 2, "y")
  local z = tableComponent(value, 3, "z")
  if not isFiniteNumber(x) or not isFiniteNumber(y) or not isFiniteNumber(z) then
    return nil, label .. " must contain three finite numbers"
  end
  if x < minimum or x > maximum or y < minimum or y > maximum or z < minimum or z > maximum then
    return nil, label .. " is outside the permitted range"
  end
  if positiveOnly and (x <= 0 or y <= 0 or z <= 0) then
    return nil, label .. " components must be positive"
  end
  return {x = x, y = y, z = z}, nil
end

local function parseQuaternion(value)
  local x = tableComponent(value, 1, "x")
  local y = tableComponent(value, 2, "y")
  local z = tableComponent(value, 3, "z")
  local w = tableComponent(value, 4, "w")
  if not isFiniteNumber(x)
    or not isFiniteNumber(y)
    or not isFiniteNumber(z)
    or not isFiniteNumber(w) then
    return nil, "rotation must contain four finite numbers"
  end

  local magnitude = math.sqrt(x * x + y * y + z * z + w * w)
  if magnitude < 0.000001 or magnitude > 1000000 then
    return nil, "rotation quaternion has an invalid magnitude"
  end
  return {x = x / magnitude, y = y / magnitude, z = z / magnitude, w = w / magnitude}, nil
end

local function parseColor(value)
  if type(value) ~= "table" then return nil, "color must be an array or object" end
  local red = tableComponent(value, 1, "r")
  local green = tableComponent(value, 2, "g")
  local blue = tableComponent(value, 3, "b")
  local alpha = tableComponent(value, 4, "a")
  if alpha == nil then alpha = 1 end
  local components = {red, green, blue, alpha}
  for _, component in ipairs(components) do
    if not isFiniteNumber(component) or component < 0 or component > 1 then
      return nil, "color components must be finite numbers from 0 through 1"
    end
  end
  return string.format("%.6f %.6f %.6f %.6f", red, green, blue, alpha), nil
end

local function parseAssetPath(value)
  if type(value) ~= "string" or #value < 5 or #value > 256 then
    return nil, "asset path must be a string of at most 256 characters"
  end
  if value:find("..", 1, true) or value:find("\\", 1, true) or value:find(":", 1, true) then
    return nil, "asset path contains a forbidden segment"
  end
  if not value:match("^[%w_/%-%.]+%.dae$") then
    return nil, "shapeName must reference a .dae asset using a virtual path"
  end
  if not value:match("^levels/")
    and not value:match("^art/")
    and not value:match("^vehicles/") then
    return nil, "shapeName must be below levels, art, or vehicles"
  end
  return value, nil
end

local function serializeFieldValue(rule, value)
  if rule.kind == "number" then
    if not isFiniteNumber(value) or value < rule.min or value > rule.max then
      return nil, "numeric field is outside the permitted range"
    end
    return string.format("%.9g", value), nil
  end
  if rule.kind == "boolean" then
    if type(value) ~= "boolean" then return nil, "field must be boolean" end
    return value and "1" or "0", nil
  end
  if rule.kind == "enum" then
    if type(value) ~= "string" or not rule.values[value] then
      return nil, "field value is not in the permitted set"
    end
    return value, nil
  end
  if rule.kind == "identifier" then
    if not validIdentifier(value) then return nil, "field must be a safe identifier" end
    return value, nil
  end
  if rule.kind == "asset_path" then return parseAssetPath(value) end
  if rule.kind == "color" then return parseColor(value) end
  return nil, "field rule is unsupported"
end

local function validateFields(className, fields)
  if fields == nil then return {}, nil end
  if type(fields) ~= "table" then return nil, "fields must be an object" end

  local classRules = FIELD_RULES[className]
  if not classRules then return nil, "class has no writable fields" end
  local serialized = {}
  for fieldName, value in pairs(fields) do
    if type(fieldName) ~= "string" or not classRules[fieldName] then
      return nil, "field is not permitted for " .. className .. ": " .. tostring(fieldName)
    end
    local fieldValue, fieldError = serializeFieldValue(classRules[fieldName], value)
    if fieldError then
      return nil, fieldName .. ": " .. fieldError
    end
    serialized[fieldName] = fieldValue
  end
  return serialized, nil
end

local function resolveObject(params)
  if type(params) ~= "table" then return nil, "params must be an object" end
  if params.id ~= nil then
    if not isInteger(params.id) or params.id < 1 then
      return nil, "id must be a positive integer"
    end
    return scenetree.findObjectById(params.id), nil
  end
  if params.name ~= nil then
    if not validIdentifier(params.name) then return nil, "name is not a safe identifier" end
    return scenetree.findObject(params.name), nil
  end
  return nil, "provide id or name"
end

local function vectorToTable(value)
  if not value then return nil end
  return {x = value.x, y = value.y, z = value.z}
end

local function quaternionToTable(value)
  if not value then return nil end
  return {x = value.x, y = value.y, z = value.z, w = value.w}
end

local function storeManagedObjectEvidence(object)
  local identityOk, objectId, objectName, className = pcall(function()
    return object:getId(), object:getName(), object:getClassName()
  end)
  if not identityOk
    or not isInteger(objectId)
    or objectId < 1
    or not validIdentifier(objectName)
    or not CREATABLE_CLASSES[className] then
    return nil, "managed object identity was invalid"
  end
  local sceneOk, byId, byName = pcall(function()
    return scenetree.findObjectById(objectId), scenetree.findObject(objectName)
  end)
  if not sceneOk or byId ~= object or byName ~= object then
    return nil, "managed object scene registration was not exact"
  end
  local existing = managedObjects[objectId]
  if existing and existing.object ~= object then
    return nil, "managed object ID is already retained by another evidence record"
  end
  local evidence = {
    object = object,
    id = objectId,
    name = objectName,
    class = className
  }
  managedObjects[objectId] = evidence
  return evidence, nil
end

local function exactManagedObjectEvidence(object)
  if not object then return nil end
  local identityOk, objectId, objectName, className = pcall(function()
    return object:getId(), object:getName(), object:getClassName()
  end)
  if not identityOk or not isInteger(objectId) or objectId < 1 then return nil end
  local evidence = managedObjects[objectId]
  if not evidence then return nil end
  local sceneOk, byId, byName = pcall(function()
    return scenetree.findObjectById(objectId), scenetree.findObject(objectName)
  end)
  if evidence.object ~= object
    or evidence.id ~= objectId
    or evidence.name ~= objectName
    or evidence.class ~= className
    or not sceneOk
    or byId ~= object
    or byName ~= object then
    -- Exact evidence is authorization, not a best-effort cache. A mismatch
    -- revokes mutation rights, but the non-authorizing tombstone must remain so
    -- extension reload cannot discard unproven live scene state.
    return nil
  end
  return evidence
end

local function managedObjectEvidenceSceneAbsent(evidence)
  local lookupOk, byId, byName = pcall(function()
    return scenetree.findObjectById(evidence.id), scenetree.findObject(evidence.name)
  end)
  if not lookupOk then return nil, "managed object deletion could not verify scene absence" end
  if byId ~= nil or byName ~= nil then
    return nil, "managed object deletion left an exact scene registration"
  end
  return true, nil
end

local function objectDescriptor(object, includeFields)
  local className = object:getClassName()
  local descriptor = {
    id = object:getId(),
    name = object:getName(),
    class = className,
    managed = exactManagedObjectEvidence(object) ~= nil
  }

  local positionOk, position = pcall(function() return object:getPosition() end)
  if positionOk then descriptor.position = vectorToTable(position) end

  local rotationOk, rotation = pcall(function() return quat(object:getRotation()) end)
  if rotationOk then descriptor.rotation = quaternionToTable(rotation) end

  local scaleOk, scale = pcall(function() return object:getScale() end)
  if scaleOk then descriptor.scale = vectorToTable(scale) end

  if includeFields then
    descriptor.fields = {}
    local readableFields = FIELD_RULES[className] or READ_ONLY_FIELD_RULES[className] or {}
    for fieldName, _ in pairs(readableFields) do
      local fieldOk, fieldValue = pcall(function() return object:getField(fieldName, 0) end)
      if fieldOk then descriptor.fields[fieldName] = fieldValue end
    end
  end
  return descriptor
end

local function ensureReadableObject(object)
  if not object then return nil, "object was not found" end
  local className = object:getClassName()
  if not (CREATABLE_CLASSES[className] or READ_ONLY_CLASSES[className]) then
    return nil, "object class is not readable through this bridge"
  end
  return className, nil
end

local function ensureWritableObject(object)
  if not object then return nil, "object was not found" end
  local className = object:getClassName()
  if not CREATABLE_CLASSES[className] then
    return nil, "object class is not writable through this bridge"
  end
  return className, nil
end

local function applyTransform(object, params)
  if params.position == nil and params.rotation == nil and params.scale == nil then
    return true, nil
  end

  local position = nil
  local rotation = nil
  local scale = nil
  local parseError = nil

  if params.position ~= nil then
    position, parseError = parseVector3(params.position, "position", -1000000, 1000000, false)
    if parseError then return false, parseError end
  else
    local current = object:getPosition()
    position = {x = current.x, y = current.y, z = current.z}
  end

  if params.rotation ~= nil then
    rotation, parseError = parseQuaternion(params.rotation)
    if parseError then return false, parseError end
  else
    local current = quat(object:getRotation())
    rotation = {x = current.x, y = current.y, z = current.z, w = current.w}
  end

  if params.scale ~= nil then
    scale, parseError = parseVector3(params.scale, "scale", 0.0001, 10000, true)
    if parseError then return false, parseError end
  end

  object:setPosRot(
    position.x,
    position.y,
    position.z,
    rotation.x,
    rotation.y,
    rotation.z,
    rotation.w
  )
  if scale then object:setScale(vec3(scale.x, scale.y, scale.z)) end
  return true, nil
end

local function applyFields(object, serializedFields)
  if type(object.preApply) == "function" then object:preApply() end
  for fieldName, value in pairs(serializedFields) do
    object:setField(fieldName, 0, value)
  end
  if type(object.setEditorDirty) == "function" then object:setEditorDirty(true) end
  if type(object.postApply) == "function" then object:postApply() end
end

local function markEditorDirty()
  if editor and type(editor.setDirty) == "function" then editor.setDirty() end
end

local function telemetrySnapshot()
  local snapshot = {
    time_seconds = elapsedSeconds,
    level = getCurrentLevelIdentifier and getCurrentLevelIdentifier() or nil,
    game_state = core_gamestate and core_gamestate.state and core_gamestate.state.state or nil,
    authenticated_peers = authenticatedPeersCount(),
    emergency_stop_available = true,
    vehicle = nil
  }

  local vehicle = getPlayerVehicle and getPlayerVehicle(0) or nil
  if vehicle then
    local position = vehicle:getPosition()
    local velocity = vehicle:getVelocity()
    local rotation = quat(vehicle:getRotation())
    snapshot.vehicle = {
      id = vehicle:getId(),
      name = vehicle:getName(),
      position = vectorToTable(position),
      rotation = quaternionToTable(rotation),
      velocity = vectorToTable(velocity),
      speed_mps = velocity:length()
    }
  end
  return snapshot
end

local HANDLERS = {}

HANDLERS["ping"] = function()
  return {
    pong = true,
    time_seconds = elapsedSeconds
  }, nil
end

HANDLERS["capabilities"] = function()
  local methods = {
    "ping",
    "capabilities",
    "telemetry.snapshot",
    "world.list_objects",
    "world.get_object",
    "world.create_object",
    "world.update_object",
    "world.delete_object",
    "world.save_level",
    "trigger.create",
    "trigger.get",
    "trigger.update",
    "trigger.list",
    "trigger.delete",
    "safety.lease_arm",
    "safety.lease_renew",
    "safety.lease_disarm",
    "extension.reload",
    "emergency_stop"
  }
  local classes = {}
  for className, _ in pairs(CREATABLE_CLASSES) do table.insert(classes, className) end
  table.sort(classes)
  return {
    schema = SCHEMA_VERSION,
    bridge_version = BRIDGE_VERSION,
    game_version = tostring(beamng_version or beamng_versionb or "unknown"),
    protocol = WEBSOCKET_PROTOCOL,
    methods = methods,
    creatable_classes = classes,
    max_payload_bytes = config.max_payload_bytes,
    telemetry_interval_seconds = config.telemetry_interval_seconds,
    safety_lease_available = true,
    safety_lease_seconds = config.safety_lease_seconds,
    safety_startup_grace_seconds = config.safety_startup_grace_seconds,
    safety_lease_armed = safetyLease ~= nil,
    persistent_map_edits_enabled = config.allow_persistent_map_edits,
    existing_map_object_edits_enabled = config.allow_existing_map_object_edits,
    editor_ready = editor ~= nil and type(editor.saveLevel) == "function"
  }, nil
end

HANDLERS["telemetry.snapshot"] = function()
  return telemetrySnapshot(), nil
end

HANDLERS["world.list_objects"] = function(params)
  local requestedClass = params.class
  if requestedClass ~= nil
    and not (CREATABLE_CLASSES[requestedClass] or READ_ONLY_CLASSES[requestedClass]) then
    return nil, protocolError("invalid_class", "class is not readable through this bridge")
  end
  local limit = params.limit or 100
  if not isInteger(limit) or limit < 1 or limit > MAX_OBJECT_RESULTS then
    return nil, protocolError("invalid_limit", "limit must be from 1 through 200")
  end
  local prefix = params.name_prefix
  if prefix ~= nil and not validIdentifier(prefix) then
    return nil, protocolError("invalid_identifier", "name_prefix is not a safe identifier")
  end

  local objects = {}
  local names = scenetree.getAllObjects() or {}
  for _, name in ipairs(names) do
    if #objects >= limit then break end
    local object = scenetree.findObject(name)
    if object then
      local className = object:getClassName()
      local nameMatches = prefix == nil or name:sub(1, #prefix) == prefix
      if (CREATABLE_CLASSES[className] or READ_ONLY_CLASSES[className])
        and (requestedClass == nil or requestedClass == className)
        and nameMatches then
        table.insert(objects, objectDescriptor(object, false))
      end
    end
  end
  return {objects = objects, count = #objects, limit = limit}, nil
end

HANDLERS["world.get_object"] = function(params)
  local object, resolveError = resolveObject(params)
  if resolveError then
    return nil, protocolError("invalid_identifier", resolveError)
  end
  local _, readableError = ensureReadableObject(object)
  if readableError then return nil, protocolError("object_unavailable", readableError) end
  return objectDescriptor(object, true), nil
end

HANDLERS["world.create_object"] = function(params)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local className = params.class
  if type(className) ~= "string" or not CREATABLE_CLASSES[className] then
    return nil, protocolError("invalid_class", "class is not in the creation allowlist")
  end
  if not validIdentifier(params.name) then
    return nil, protocolError("invalid_identifier", "name is not a safe identifier")
  end
  if scenetree.findObject(params.name) then
    return nil, protocolError("object_exists", "an object with that name already exists")
  end
  if not scenetree.MissionGroup then
    return nil, protocolError("level_unavailable", "a level with MissionGroup must be loaded")
  end

  local serializedFields, fieldsError = validateFields(className, params.fields)
  if fieldsError then return nil, protocolError("invalid_fields", fieldsError) end
  if className == "TSStatic" and not serializedFields.shapeName then
    return nil, protocolError("missing_field", "TSStatic requires fields.shapeName")
  end

  local object = createObject(className)
  if not object then return nil, protocolError("create_failed", "BeamNG did not create the object") end

  local ok, createError = pcall(function()
    applyFields(object, serializedFields)
    object.canSave = true
    object:registerObject(params.name)
    scenetree.MissionGroup:addObject(object)
    local transformOk, transformError = applyTransform(object, params)
    if not transformOk then error(transformError) end
  end)
  if not ok then
    pcall(function() object:delete() end)
    return nil, protocolError("create_failed", "object creation failed", {reason = tostring(createError)})
  end

  local evidence, evidenceError = storeManagedObjectEvidence(object)
  if not evidence then
    pcall(function() object:delete() end)
    return nil, protocolError(
      "create_failed",
      "object creation could not retain exact management evidence",
      {reason = tostring(evidenceError)}
    )
  end
  markEditorDirty()
  return objectDescriptor(object, true), nil
end

local function ensureManagedMutation(object)
  local evidence = exactManagedObjectEvidence(object)
  if evidence then return true, nil, evidence end
  if config.allow_existing_map_object_edits then
    return true, nil, nil
  end
  return nil, "existing map object edits are disabled by configuration", nil
end

HANDLERS["world.update_object"] = function(params)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local object, resolveError = resolveObject(params)
  if resolveError then return nil, protocolError("invalid_identifier", resolveError) end
  local className, writableError = ensureWritableObject(object)
  if writableError then return nil, protocolError("object_unavailable", writableError) end
  local _, managedError, managedEvidence = ensureManagedMutation(object)
  if managedError then
    return nil, protocolError("existing_object_edits_disabled", managedError)
  end

  local serializedFields, fieldsError = validateFields(className, params.fields)
  if fieldsError then return nil, protocolError("invalid_fields", fieldsError) end

  if params.new_name ~= nil then
    if not validIdentifier(params.new_name) then
      return nil, protocolError("invalid_identifier", "new_name is not a safe identifier")
    end
    local existing = scenetree.findObject(params.new_name)
    if existing and existing:getId() ~= object:getId() then
      return nil, protocolError("object_exists", "an object with new_name already exists")
    end
  end

  local ok, updateError = pcall(function()
    applyFields(object, serializedFields)
    local transformOk, transformError = applyTransform(object, params)
    if not transformOk then error(transformError) end
    if params.new_name then object:setName(params.new_name) end
  end)
  if not ok then
    return nil, protocolError("update_failed", "object update failed", {reason = tostring(updateError)})
  end
  if managedEvidence then
    local refreshed, refreshError = storeManagedObjectEvidence(object)
    if not refreshed then
      return nil, protocolError(
        "update_failed",
        "object update lost exact mutation authority; retained evidence blocks bridge reload",
        {reason = tostring(refreshError)}
      )
    end
  end
  markEditorDirty()
  return objectDescriptor(object, true), nil
end

HANDLERS["world.delete_object"] = function(params)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  if params.confirm ~= true then
    return nil, protocolError("confirmation_required", "set confirm to true to delete an object")
  end
  local object, resolveError = resolveObject(params)
  if resolveError then return nil, protocolError("invalid_identifier", resolveError) end
  local _, writableError = ensureWritableObject(object)
  if writableError then return nil, protocolError("object_unavailable", writableError) end
  local _, managedError, managedEvidence = ensureManagedMutation(object)
  if managedError then
    return nil, protocolError("existing_object_edits_disabled", managedError)
  end

  local objectId = object:getId()
  local objectName = object:getName()
  local ok, deleted = pcall(function()
    if editor and type(editor.deleteObject) == "function" then
      return editor.deleteObject(objectId)
    end
    object:deleteObject()
    return true
  end)
  if not ok or deleted == false then
    return nil, protocolError("delete_failed", "BeamNG did not delete the object")
  end
  if managedEvidence then
    local absent, absenceError = managedObjectEvidenceSceneAbsent(managedEvidence)
    if not absent then
      return nil, protocolError("delete_failed", absenceError)
    end
    if managedObjects[objectId] == managedEvidence then managedObjects[objectId] = nil end
  end
  markEditorDirty()
  return {deleted = true, id = objectId, name = objectName}, nil
end

HANDLERS["world.save_level"] = function(params)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  if not config.allow_persistent_map_edits then
    return nil, protocolError(
      "persistent_edits_disabled",
      "allow_persistent_map_edits is disabled in the Lua bridge configuration"
    )
  end
  if params.confirm ~= true then
    return nil, protocolError("confirmation_required", "set confirm to true to save the level")
  end
  if type(params.level) ~= "string" or #params.level < 1 then
    return nil, protocolError(
      "level_required",
      "level must be the exact non-empty identifier of the loaded level"
    )
  end
  if not editor or type(editor.saveLevel) ~= "function" then
    return nil, protocolError("editor_unavailable", "World Editor must be initialized")
  end

  local level = getCurrentLevelIdentifier and getCurrentLevelIdentifier() or nil
  if not level then return nil, protocolError("level_unavailable", "no current level is loaded") end
  if params.level ~= level then
    return nil, protocolError("level_mismatch", "confirmed level does not match the loaded level")
  end

  local ok, saveResult = pcall(editor.saveLevel)
  if not ok or saveResult == false then
    return nil, protocolError(
      "save_failed",
      "World Editor failed to save",
      {reason = tostring(saveResult)}
    )
  end
  -- BeamNG 0.38's editor.saveLevel() does not return the underlying
  -- serialization status. A non-throwing call proves only that the save was
  -- requested, so never claim durable success to the MCP client.
  return {
    save_requested = true,
    verified = false,
    verification = "BeamNG editor API does not expose serialization status",
    level = level
  }, nil
end

HANDLERS["extension.reload"] = function(params)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local extensionName = params.name or "beamng_mcp/bridge"
  local canonicalName = type(extensionName) == "string"
    and RELOADABLE_EXTENSIONS[extensionName]
    or nil
  if not canonicalName then
    return nil, protocolError("extension_not_allowed", "extension is not in the reload allowlist")
  end
  if next(managedTriggers) ~= nil then
    return nil, protocolError(
      "managed_triggers_active",
      "delete every managed trigger draft and quarantine before reloading the bridge"
    )
  end
  if next(managedObjects) ~= nil then
    return nil, protocolError(
      "managed_objects_active",
      "delete every bridge-managed map object before reloading the bridge"
    )
  end
  pendingReload = canonicalName
  return {scheduled = true, name = extensionName}, nil
end

local function stopVehicle(vehicle)
  local command = table.concat({
    "if ai then ai.setMode('disabled') end",
    "input.event('throttle', 0, 1)",
    "input.event('brake', 1, 1)",
    "input.event('parkingbrake', 1, 1)"
  }, ";")
  vehicle:queueLuaCommand(command)
  return vehicle:getId()
end

local function findVehicleById(vehicleId)
  for _, vehicle in ipairs(getAllVehicles()) do
    if vehicle:getId() == vehicleId then return vehicle end
  end
  return nil
end

local function findVehicleByName(vehicleName)
  for _, vehicle in ipairs(getAllVehicles()) do
    if vehicle:getName() == vehicleName then return vehicle end
  end
  return nil
end

-- BeamNGTrigger is intentionally not part of CREATABLE_CLASSES or FIELD_RULES.
-- Triggers have a separate, closed schema because their luaFunction field is an
-- execution primitive. The bridge creates only the fixed onBeamNGTrigger hook.
local TRIGGER_CREATE_KEYS = {
  handle = true,
  shape = true,
  position = true,
  rotation = true,
  scale = true,
  mode = true,
  test_type = true,
  debug = true,
  action = true
}

local TRIGGER_UPDATE_KEYS = {
  handle = true,
  position = true,
  rotation = true,
  scale = true,
  mode = true,
  test_type = true,
  debug = true,
  action = true,
  enabled = true
}

local TRIGGER_MODE_FIELDS = {
  center = "Center",
  contains = "Contains",
  overlaps = "Overlaps"
}

local TRIGGER_TEST_TYPE_FIELDS = {
  race_corners = "Race corners",
  bounding_box = "Bounding box"
}

local TRIGGER_ACTION_EVENTS = {
  enter = true,
  exit = true
}

local function validateExactObject(value, allowedKeys, requiredKeys, label)
  if type(value) ~= "table" then return nil, label .. " must be an object" end
  for key, _ in pairs(value) do
    if type(key) ~= "string" or not allowedKeys[key] then
      return nil, label .. " contains an unknown field: " .. tostring(key)
    end
  end
  for key, _ in pairs(requiredKeys or {}) do
    if value[key] == nil then return nil, label .. " requires " .. key end
  end
  return true, nil
end

local function validateTriggerHandle(handle)
  if type(handle) ~= "string" or #handle ~= 36 or handle:sub(1, 4) ~= "trg_" then
    return nil, "handle must be trg_ followed by 32 lowercase hexadecimal characters"
  end
  if not handle:sub(5):match("^[0-9a-f]+$") then
    return nil, "handle must be trg_ followed by 32 lowercase hexadecimal characters"
  end
  return true, nil
end

local function triggerNameForHandle(handle)
  return "beamng_mcp_trigger_" .. handle:sub(5)
end

local function parseExactVector3(value, label, minimum, maximum, positiveOnly)
  local valid, objectError = validateExactObject(
    value,
    {x = true, y = true, z = true},
    {x = true, y = true, z = true},
    label
  )
  if not valid then return nil, objectError end
  local components = {value.x, value.y, value.z}
  for _, component in ipairs(components) do
    if not isFiniteNumber(component) or component < minimum or component > maximum then
      return nil, label .. " components must be finite numbers inside the permitted range"
    end
    if positiveOnly and component <= 0 then
      return nil, label .. " components must be positive"
    end
  end
  return {x = value.x, y = value.y, z = value.z}, nil
end

local function parseExactQuaternion(value)
  local valid, objectError = validateExactObject(
    value,
    {x = true, y = true, z = true, w = true},
    {x = true, y = true, z = true, w = true},
    "rotation"
  )
  if not valid then return nil, objectError end
  local components = {value.x, value.y, value.z, value.w}
  for _, component in ipairs(components) do
    if not isFiniteNumber(component) or component < -1000000 or component > 1000000 then
      return nil, "rotation components must be finite and bounded"
    end
  end
  local magnitude = math.sqrt(
    value.x * value.x + value.y * value.y + value.z * value.z + value.w * value.w
  )
  if magnitude < 0.000001 or magnitude > 1000000 then
    return nil, "rotation quaternion has an invalid magnitude"
  end
  return {
    x = value.x / magnitude,
    y = value.y / magnitude,
    z = value.z / magnitude,
    w = value.w / magnitude
  }, nil
end

local function parseTriggerAction(value)
  local valid, objectError = validateExactObject(
    value,
    {type = true, events = true},
    {type = true, events = true},
    "action"
  )
  if not valid then return nil, objectError end
  if value.type ~= "emit_bridge_event" then
    return nil, "action.type must be emit_bridge_event"
  end
  if type(value.events) ~= "table" then return nil, "action.events must be an array" end

  local count = 0
  for key, _ in pairs(value.events) do
    if not isInteger(key) or key < 1 or key > 2 then
      return nil, "action.events must be a compact array with at most two entries"
    end
    count = count + 1
  end
  if count < 1 or count > 2 then
    return nil, "action.events must contain one or two entries"
  end

  local events = {}
  local eventSet = {}
  for index = 1, count do
    local eventName = value.events[index]
    if not TRIGGER_ACTION_EVENTS[eventName] then
      return nil, "action.events supports only enter and exit"
    end
    if eventSet[eventName] then return nil, "action.events entries must be unique" end
    eventSet[eventName] = true
    table.insert(events, eventName)
  end
  if #events ~= count then return nil, "action.events must not contain gaps" end
  return {
    type = "emit_bridge_event",
    events = events,
    event_set = eventSet
  }, nil
end

local function copyTriggerAction(action)
  local events = {}
  local eventSet = {}
  for _, eventName in ipairs(action.events) do
    table.insert(events, eventName)
    eventSet[eventName] = true
  end
  return {type = "emit_bridge_event", events = events, event_set = eventSet}
end

local function copyTriggerRecord(record)
  return {
    handle = record.handle,
    name = record.name,
    owner = record.owner,
    generation = record.generation,
    shape = record.shape,
    position = shallowCopy(record.position),
    rotation = shallowCopy(record.rotation),
    scale = shallowCopy(record.scale),
    mode = record.mode,
    test_type = record.test_type,
    debug = record.debug,
    action = copyTriggerAction(record.action),
    object = record.object,
    object_id = record.object_id,
    object_name = record.object_name,
    object_class = record.object_class,
    occupancy = shallowCopy(record.occupancy),
    sequence = record.sequence,
    count = record.count,
    last_event = record.last_event and shallowCopy(record.last_event) or nil,
    rate_window_started = record.rate_window_started,
    rate_count = record.rate_count,
    quarantined = record.quarantined == true,
    quarantine_reason = record.quarantine_reason,
    quarantined_at = record.quarantined_at
  }
end

local function triggerDescriptor(record)
  local descriptor = {
    handle = record.handle,
    engine_name = record.name,
    shape = record.shape,
    position = shallowCopy(record.position),
    rotation = shallowCopy(record.rotation),
    scale = shallowCopy(record.scale),
    mode = record.mode,
    test_type = record.test_type,
    debug = record.debug,
    action = {
      type = record.action.type,
      events = {unpack(record.action.events)}
    },
    enabled = record.object ~= nil,
    persistent = false,
    sequence = record.sequence,
    count = record.count
  }
  if record.object_id then descriptor.object_id = record.object_id end
  if record.last_event then descriptor.last_event = shallowCopy(record.last_event) end
  return descriptor
end

local function countTriggersForPeer(peerId)
  local count = 0
  for _, record in pairs(managedTriggers) do
    if record.owner == peerId then count = count + 1 end
  end
  return count
end

local function countManagedTriggers()
  local count = 0
  -- Quarantined records deliberately remain in managedTriggers and therefore
  -- consume this global quota until exact deletion or verified mission absence.
  for _ in pairs(managedTriggers) do count = count + 1 end
  return count
end

local function ownedTrigger(handle, peerId)
  local valid, handleError = validateTriggerHandle(handle)
  if not valid then return nil, protocolError("invalid_handle", handleError) end
  local record = managedTriggers[handle]
  if not record or record.owner ~= peerId then
    return nil, protocolError("trigger_not_found", "trigger was not found")
  end
  return record, nil
end

local function exactLiveTrigger(record)
  if not record.object or not record.object_id then return nil, "trigger is not enabled" end
  local ok, objectId, objectName, className = pcall(function()
    return record.object:getId(), record.object:getName(), record.object:getClassName()
  end)
  if not ok
    or objectId ~= record.object_id
    or objectName ~= record.object_name
    or objectName ~= record.name
    or className ~= record.object_class
    or className ~= "BeamNGTrigger" then
    return nil, "live trigger identity changed"
  end
  local sceneOk, byId, byName = pcall(function()
    return scenetree.findObjectById(objectId), scenetree.findObject(objectName)
  end)
  if not sceneOk then return nil, "live trigger scene lookup failed" end
  if byId ~= record.object or byName ~= record.object then
    return nil, "live trigger scene registration changed"
  end
  local nameRegistration = managedTriggerNames[objectName]
  local idRegistration = managedTriggerIds[objectId]
  if not nameRegistration
    or not idRegistration
    or nameRegistration.handle ~= record.handle
    or idRegistration.handle ~= record.handle
    or nameRegistration.generation ~= record.generation
    or idRegistration.generation ~= record.generation then
    return nil, "live trigger registry generation changed"
  end
  return record.object, nil
end

local function quarantineTrigger(record, reason, failure)
  -- Preserve every exact reference and registry entry for a later cleanup
  -- retry. Removing those records while a live engine object may remain would
  -- lose the only evidence that the bridge owns it.
  record.quarantined = true
  record.owner = nil
  record.occupancy = {}
  record.quarantine_reason = tostring(reason) .. ": " .. tostring(failure)
  record.quarantined_at = realElapsedSeconds
  return nil, failure
end

local function clearExactTriggerRegistrations(record)
  local nameRegistration = managedTriggerNames[record.name]
  if nameRegistration
    and nameRegistration.handle == record.handle
    and nameRegistration.generation == record.generation then
    managedTriggerNames[record.name] = nil
  end
  if record.object_id then
    local idRegistration = managedTriggerIds[record.object_id]
    if idRegistration
      and idRegistration.handle == record.handle
      and idRegistration.generation == record.generation then
      managedTriggerIds[record.object_id] = nil
    end
  end
end

local function clearTriggerObjectEvidence(record)
  record.object = nil
  record.object_id = nil
  record.object_name = nil
  record.object_class = nil
  record.occupancy = {}
end

local function captureTriggerObjectEvidence(record)
  if not record.object then return nil, nil, nil, nil end
  local ok, objectId, objectName, className = pcall(function()
    return record.object:getId(), record.object:getName(), record.object:getClassName()
  end)
  if not ok then return nil, nil, nil, nil end
  if isInteger(objectId) and objectId >= 1 then record.object_id = objectId end
  if type(objectName) == "string" and #objectName > 0 then
    record.object_name = objectName
  end
  if type(className) == "string" and #className > 0 then
    record.object_class = className
  end
  return true, objectId, objectName, className
end

local function lookupTriggerSceneEvidence(record)
  return pcall(function()
    local byId = nil
    if isInteger(record.object_id) and record.object_id >= 1 then
      byId = scenetree.findObjectById(record.object_id)
    end
    local byName = scenetree.findObject(record.name)
    local byObjectName = nil
    if type(record.object_name) == "string"
      and #record.object_name > 0
      and record.object_name ~= record.name then
      byObjectName = scenetree.findObject(record.object_name)
    end
    return byId, byName, byObjectName
  end)
end

local function retainExactTriggerRegistrations(record)
  local lookupOk, byId, byName = lookupTriggerSceneEvidence(record)
  if not lookupOk then return end
  if byName == record.object then
    managedTriggerNames[record.name] = {
      handle = record.handle,
      generation = record.generation
    }
  end
  if record.object_id and byId == record.object then
    managedTriggerIds[record.object_id] = {
      handle = record.handle,
      generation = record.generation
    }
  end
end

local function triggerScalarNear(actual, expected, absoluteTolerance, relativeTolerance)
  if not isFiniteNumber(actual) or not isFiniteNumber(expected) then return false end
  local magnitude = math.max(math.abs(actual), math.abs(expected))
  return math.abs(actual - expected)
    <= absoluteTolerance + relativeTolerance * magnitude
end

local function triggerVectorNear(actual, expected, absoluteTolerance)
  if not actual or not expected then return false end
  return triggerScalarNear(
    actual.x,
    expected.x,
    absoluteTolerance,
    TRIGGER_VECTOR_RELATIVE_TOLERANCE
  )
    and triggerScalarNear(
      actual.y,
      expected.y,
      absoluteTolerance,
      TRIGGER_VECTOR_RELATIVE_TOLERANCE
    )
    and triggerScalarNear(
      actual.z,
      expected.z,
      absoluteTolerance,
      TRIGGER_VECTOR_RELATIVE_TOLERANCE
    )
end

local function triggerQuaternionNear(actual, expected)
  if not actual or not expected then return false end
  local direct = triggerScalarNear(
    actual.x,
    expected.x,
    TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
    0
  )
    and triggerScalarNear(
      actual.y,
      expected.y,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
    and triggerScalarNear(
      actual.z,
      expected.z,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
    and triggerScalarNear(
      actual.w,
      expected.w,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
  if direct then return true end
  return triggerScalarNear(
    actual.x,
    -expected.x,
    TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
    0
  )
    and triggerScalarNear(
      actual.y,
      -expected.y,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
    and triggerScalarNear(
      actual.z,
      -expected.z,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
    and triggerScalarNear(
      actual.w,
      -expected.w,
      TRIGGER_ROTATION_ABSOLUTE_TOLERANCE,
      0
    )
end

local function verifyTriggerTransformReadback(record, object)
  local readOk, matches = pcall(function()
    local position = object:getPosition()
    local rotation = quat(object:getRotation())
    local scale = object:getScale()
    return triggerVectorNear(
      position,
      record.position,
      TRIGGER_POSITION_ABSOLUTE_TOLERANCE
    )
      and triggerQuaternionNear(rotation, record.rotation)
      and triggerVectorNear(scale, record.scale, TRIGGER_SCALE_ABSOLUTE_TOLERANCE)
  end)
  if not readOk then return nil, "BeamNG trigger transform readback failed" end
  if not matches then
    return nil, "BeamNG trigger transform did not match the requested collision volume"
  end
  return true, nil
end

local function deleteTriggerObjectAndProveAbsent(record)
  if not record.object then return true, nil end
  local identityOk = captureTriggerObjectEvidence(record)
  local deleteOk, deleteResult = pcall(function() return record.object:delete() end)
  local lookupOk, byId, byName, byObjectName = lookupTriggerSceneEvidence(record)
  if not identityOk then return nil, "trigger deletion could not capture exact object identity" end
  if not deleteOk then return nil, "BeamNG trigger deletion raised an error" end
  if deleteResult == false then return nil, "BeamNG rejected trigger deletion" end
  if not lookupOk then return nil, "trigger deletion could not verify scene absence" end
  if byId ~= nil or byName ~= nil or byObjectName ~= nil then
    return nil, "trigger deletion did not remove every exact scene registration"
  end
  return true, nil
end

local function rollbackTriggerInstantiation(record, previousRecord, failure)
  local deleted, deleteError = deleteTriggerObjectAndProveAbsent(record)
  if deleted then
    clearExactTriggerRegistrations(record)
    clearTriggerObjectEvidence(record)
    managedTriggers[record.handle] = previousRecord
    return nil, failure
  end

  retainExactTriggerRegistrations(record)
  managedTriggers[record.handle] = record
  quarantineTrigger(
    record,
    "trigger_enable_rollback_failed",
    tostring(failure) .. "; " .. tostring(deleteError)
  )
  return nil,
    tostring(failure) .. "; rollback could not prove trigger deletion: " .. tostring(deleteError)
end

local function instantiateTrigger(record)
  if record.object then return nil, "trigger is already enabled" end
  if not scenetree.MissionGroup then
    return nil, "a level with MissionGroup must be loaded"
  end
  if scenetree.findObject(record.name) then
    return nil, "the reserved trigger name is already present in the scene"
  end
  if managedTriggerNames[record.name] then
    return nil, "the reserved trigger name is already registered"
  end

  local previousRecord = managedTriggers[record.handle]
  managedTriggers[record.handle] = record
  local createOk, object = pcall(function() return createObject("BeamNGTrigger") end)
  if not createOk or not object then
    managedTriggers[record.handle] = previousRecord
    return nil, "BeamNG did not create the trigger"
  end
  record.object = object
  captureTriggerObjectEvidence(record)
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    if type(object.setCanSave) == "function" then object:setCanSave(false) end
    object.canSave = false
    object:setField("canSave", 0, "0")
    object:setField("luaFunction", 0, "onBeamNGTrigger")
    object:setField("triggerType", 0, "Box")
    object:setField("triggerMode", 0, TRIGGER_MODE_FIELDS[record.mode])
    object:setField("triggerTestType", 0, TRIGGER_TEST_TYPE_FIELDS[record.test_type])
    object:setField("ticking", 0, "0")
    object:setField("debug", 0, record.debug and "1" or "0")
    if type(object.postApply) == "function" then object:postApply() end
    object:registerObject(record.name)
    scenetree.MissionGroup:addObject(object)
    object:setPosRot(
      record.position.x,
      record.position.y,
      record.position.z,
      record.rotation.x,
      record.rotation.y,
      record.rotation.z,
      record.rotation.w
    )
    object:setScale(vec3(record.scale.x, record.scale.y, record.scale.z))
  end)
  if not ok then
    return rollbackTriggerInstantiation(
      record,
      previousRecord,
      "trigger creation failed: " .. tostring(createError)
    )
  end

  local identityOk, objectId, objectName, className = captureTriggerObjectEvidence(record)
  if not identityOk
    or not isInteger(objectId)
    or objectId < 1
    or objectName ~= record.name
    or className ~= "BeamNGTrigger" then
    return rollbackTriggerInstantiation(
      record,
      previousRecord,
      "BeamNG registered an unexpected trigger identity"
    )
  end
  local sceneOk, byId, byName = lookupTriggerSceneEvidence(record)
  if not sceneOk or byId ~= object or byName ~= object then
    return rollbackTriggerInstantiation(
      record,
      previousRecord,
      "BeamNG did not expose the exact registered trigger in the scene"
    )
  end
  local transformVerified, transformError = verifyTriggerTransformReadback(record, object)
  if not transformVerified then
    return rollbackTriggerInstantiation(record, previousRecord, transformError)
  end

  record.occupancy = {}
  managedTriggerNames[record.name] = {
    handle = record.handle,
    generation = record.generation
  }
  managedTriggerIds[objectId] = {
    handle = record.handle,
    generation = record.generation
  }
  return true, nil
end

local function disableTrigger(record)
  local object, identityError = exactLiveTrigger(record)
  if not object then return nil, identityError end
  -- Unregister before deletion so any synchronous exit hook emitted by the
  -- engine during teardown cannot escape as an owner event.
  local nameRegistration = managedTriggerNames[record.name]
  local idRegistration = managedTriggerIds[record.object_id]
  managedTriggerNames[record.name] = nil
  managedTriggerIds[record.object_id] = nil
  local deleted, deleteError = deleteTriggerObjectAndProveAbsent(record)
  if not deleted then
    managedTriggerNames[record.name] = nameRegistration
    managedTriggerIds[record.object_id] = idRegistration
    return nil, deleteError
  end
  clearTriggerObjectEvidence(record)
  return true, nil
end

local function cleanupTriggerRecord(handle, reason)
  local record = managedTriggers[handle]
  if not record then return true, nil end
  if record.object then
    local disabled, disableError = disableTrigger(record)
    if not disabled then
      quarantineTrigger(record, reason, disableError)
      log(
        "W",
        LOG_TAG,
        "Quarantined an event-silent managed trigger during "
          .. tostring(reason)
          .. ": "
          .. tostring(disableError)
      )
      return nil, disableError
    end
  end
  clearExactTriggerRegistrations(record)
  managedTriggers[handle] = nil
  return true, nil
end

local function cleanupTriggersForPeer(peerId, reason)
  local handles = {}
  for handle, record in pairs(managedTriggers) do
    if record.owner == peerId then table.insert(handles, handle) end
  end
  local allClean = true
  local failures = 0
  for _, handle in ipairs(handles) do
    local cleaned = cleanupTriggerRecord(handle, reason)
    if not cleaned then
      allClean = false
      failures = failures + 1
    end
  end
  return allClean, failures
end

local function cleanupAllTriggers(reason)
  local handles = {}
  for handle, _ in pairs(managedTriggers) do table.insert(handles, handle) end
  local allClean = true
  local failures = 0
  for _, handle in ipairs(handles) do
    local cleaned = cleanupTriggerRecord(handle, reason)
    if not cleaned then
      allClean = false
      failures = failures + 1
    end
  end
  return allClean, failures
end

local function releaseGoneQuarantinedTriggers(reason)
  local released = 0
  local handles = {}
  for handle, record in pairs(managedTriggers) do
    if record.quarantined then table.insert(handles, handle) end
  end
  for _, handle in ipairs(handles) do
    local record = managedTriggers[handle]
    local lookupOk, byId, byName, byObjectName = lookupTriggerSceneEvidence(record)
    -- A mission teardown is the one external boundary that can remove an
    -- identity-tampered object for us. Retire evidence only after every exact
    -- ID, reserved-name, and observed-name lookup proves that no object remains.
    if lookupOk and byId == nil and byName == nil and byObjectName == nil then
      clearExactTriggerRegistrations(record)
      managedTriggers[handle] = nil
      released = released + 1
      log(
        "I",
        LOG_TAG,
        "Released absent quarantined trigger after " .. tostring(reason)
      )
    end
  end
  return released
end

local function parseTriggerCreate(params, peerId)
  local valid, paramsError = validateExactObject(
    params,
    TRIGGER_CREATE_KEYS,
    TRIGGER_CREATE_KEYS,
    "trigger.create params"
  )
  if not valid then return nil, paramsError end
  local handleOk, handleError = validateTriggerHandle(params.handle)
  if not handleOk then return nil, handleError end
  if params.shape ~= "box" then return nil, "shape must be box" end
  if type(params.debug) ~= "boolean" then return nil, "debug must be boolean" end
  if not TRIGGER_MODE_FIELDS[params.mode] then
    return nil, "mode must be center, contains, or overlaps"
  end
  if not TRIGGER_TEST_TYPE_FIELDS[params.test_type] then
    return nil, "test_type must be race_corners or bounding_box"
  end

  local position, positionError = parseExactVector3(
    params.position,
    "position",
    -1000000,
    1000000,
    false
  )
  if not position then return nil, positionError end
  local rotation, rotationError = parseExactQuaternion(params.rotation)
  if not rotation then return nil, rotationError end
  local scale, scaleError = parseExactVector3(params.scale, "scale", 0.0001, 10000, true)
  if not scale then return nil, scaleError end
  local action, actionError = parseTriggerAction(params.action)
  if not action then return nil, actionError end

  triggerGeneration = triggerGeneration + 1
  return {
    handle = params.handle,
    name = triggerNameForHandle(params.handle),
    owner = peerId,
    generation = triggerGeneration,
    shape = "box",
    position = position,
    rotation = rotation,
    scale = scale,
    mode = params.mode,
    test_type = params.test_type,
    debug = params.debug,
    action = action,
    object = nil,
    object_id = nil,
    object_name = nil,
    object_class = nil,
    occupancy = {},
    sequence = 0,
    count = 0,
    last_event = nil,
    rate_window_started = realElapsedSeconds,
    rate_count = 0,
    quarantined = false,
    quarantine_reason = nil,
    quarantined_at = nil
  }, nil
end

local function applyTriggerPatch(candidate, params)
  if params.position ~= nil then
    local value, valueError = parseExactVector3(
      params.position,
      "position",
      -1000000,
      1000000,
      false
    )
    if not value then return nil, valueError end
    candidate.position = value
  end
  if params.rotation ~= nil then
    local value, valueError = parseExactQuaternion(params.rotation)
    if not value then return nil, valueError end
    candidate.rotation = value
  end
  if params.scale ~= nil then
    local value, valueError = parseExactVector3(params.scale, "scale", 0.0001, 10000, true)
    if not value then return nil, valueError end
    candidate.scale = value
  end
  if params.mode ~= nil then
    if not TRIGGER_MODE_FIELDS[params.mode] then
      return nil, "mode must be center, contains, or overlaps"
    end
    candidate.mode = params.mode
  end
  if params.test_type ~= nil then
    if not TRIGGER_TEST_TYPE_FIELDS[params.test_type] then
      return nil, "test_type must be race_corners or bounding_box"
    end
    candidate.test_type = params.test_type
  end
  if params.debug ~= nil then
    if type(params.debug) ~= "boolean" then return nil, "debug must be boolean" end
    candidate.debug = params.debug
  end
  if params.action ~= nil then
    local value, valueError = parseTriggerAction(params.action)
    if not value then return nil, valueError end
    candidate.action = value
  end
  return candidate, nil
end

HANDLERS["trigger.create"] = function(params, peerId)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local record, parseError = parseTriggerCreate(params, peerId)
  if not record then return nil, protocolError("invalid_trigger", parseError) end
  if managedTriggers[record.handle] then
    return nil, protocolError("trigger_exists", "trigger handle already exists")
  end
  if countManagedTriggers() >= MAX_MANAGED_TRIGGERS_TOTAL then
    return nil, protocolError("trigger_quota_exceeded", "global managed trigger quota reached")
  end
  if countTriggersForPeer(peerId) >= MAX_MANAGED_TRIGGERS_PER_PEER then
    return nil, protocolError("trigger_quota_exceeded", "managed trigger quota reached")
  end
  if managedTriggerNames[record.name] or scenetree.findObject(record.name) then
    return nil, protocolError("trigger_name_collision", "reserved trigger name is unavailable")
  end
  managedTriggers[record.handle] = record
  return triggerDescriptor(record), nil
end

HANDLERS["trigger.get"] = function(params, peerId)
  local valid, paramsError = validateExactObject(
    params,
    {handle = true},
    {handle = true},
    "trigger.get params"
  )
  if not valid then return nil, protocolError("invalid_params", paramsError) end
  local record, recordError = ownedTrigger(params.handle, peerId)
  if not record then return nil, recordError end
  return triggerDescriptor(record), nil
end

HANDLERS["trigger.list"] = function(params, peerId)
  local valid, paramsError = validateExactObject(
    params,
    {limit = true},
    {},
    "trigger.list params"
  )
  if not valid then return nil, protocolError("invalid_params", paramsError) end
  local limit = params.limit or MAX_TRIGGER_RESULTS
  if not isInteger(limit) or limit < 1 or limit > MAX_TRIGGER_RESULTS then
    return nil, protocolError("invalid_limit", "limit must be from 1 through 100")
  end
  local handles = {}
  for handle, record in pairs(managedTriggers) do
    if record.owner == peerId then table.insert(handles, handle) end
  end
  table.sort(handles)
  local descriptors = {}
  for _, handle in ipairs(handles) do
    if #descriptors >= limit then break end
    table.insert(descriptors, triggerDescriptor(managedTriggers[handle]))
  end
  return {triggers = descriptors, count = #descriptors, limit = limit}, nil
end

HANDLERS["trigger.update"] = function(params, peerId)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local valid, paramsError = validateExactObject(
    params,
    TRIGGER_UPDATE_KEYS,
    {handle = true},
    "trigger.update params"
  )
  if not valid then return nil, protocolError("invalid_params", paramsError) end
  if params.enabled ~= nil and type(params.enabled) ~= "boolean" then
    return nil, protocolError("invalid_trigger", "enabled must be boolean")
  end

  local record, recordError = ownedTrigger(params.handle, peerId)
  if not record then return nil, recordError end
  local hasPatch = params.position ~= nil
    or params.rotation ~= nil
    or params.scale ~= nil
    or params.mode ~= nil
    or params.test_type ~= nil
    or params.debug ~= nil
    or params.action ~= nil

  if record.object then
    if hasPatch then
      return nil, protocolError(
        "trigger_enabled",
        "enabled triggers are immutable; disable the trigger before editing"
      )
    end
    if params.enabled == false then
      local disabled, disableError = disableTrigger(record)
      if not disabled then
        quarantineTrigger(record, "owner_disable_failed", disableError)
        return nil, protocolError("trigger_identity_mismatch", disableError)
      end
      return triggerDescriptor(record), nil
    end
    if params.enabled == true then return triggerDescriptor(record), nil end
    return nil, protocolError("empty_update", "provide enabled=false to disable the trigger")
  end

  if not hasPatch and params.enabled == nil then
    return nil, protocolError("empty_update", "provide at least one trigger field or enabled state")
  end
  local candidate = copyTriggerRecord(record)
  local patched, patchError = applyTriggerPatch(candidate, params)
  if not patched then return nil, protocolError("invalid_trigger", patchError) end
  if params.enabled == true then
    local instantiated, createError = instantiateTrigger(candidate)
    if not instantiated then return nil, protocolError("trigger_enable_failed", createError) end
  end
  managedTriggers[record.handle] = candidate
  return triggerDescriptor(candidate), nil
end

HANDLERS["trigger.delete"] = function(params, peerId)
  local reloadError = pendingReloadMutationError()
  if reloadError then return nil, reloadError end
  local valid, paramsError = validateExactObject(
    params,
    {handle = true, confirm = true},
    {handle = true, confirm = true},
    "trigger.delete params"
  )
  if not valid then return nil, protocolError("invalid_params", paramsError) end
  if params.confirm ~= true then
    return nil, protocolError("confirmation_required", "set confirm to true to delete a trigger")
  end
  local record, recordError = ownedTrigger(params.handle, peerId)
  if not record then return nil, recordError end
  if record.object then
    local disabled, disableError = disableTrigger(record)
    if not disabled then
      quarantineTrigger(record, "owner_delete_failed", disableError)
      return nil, protocolError("trigger_identity_mismatch", disableError)
    end
  end
  managedTriggerNames[record.name] = nil
  managedTriggers[record.handle] = nil
  return {deleted = true, handle = record.handle}, nil
end

local function onBeamNGTrigger(data)
  if type(data) ~= "table" then return end
  if data.event ~= "enter" and data.event ~= "exit" then return end
  if not isInteger(data.triggerID) or data.triggerID < 1 then return end
  if type(data.triggerName) ~= "string" or #data.triggerName > MAX_IDENTIFIER_LENGTH then return end

  local nameRegistration = managedTriggerNames[data.triggerName]
  local idRegistration = managedTriggerIds[data.triggerID]
  if not nameRegistration or not idRegistration then return end
  if nameRegistration.handle ~= idRegistration.handle
    or nameRegistration.generation ~= idRegistration.generation then
    return
  end
  local record = managedTriggers[nameRegistration.handle]
  if not record then return end
  if record.quarantined then return end
  if record.generation ~= nameRegistration.generation then return end
  if record.object_id ~= data.triggerID or record.name ~= data.triggerName then return end
  local object = exactLiveTrigger(record)
  if not object then return end
  local peer = peers[record.owner]
  if not peer or not peer.authenticated then return end

  if not isInteger(data.subjectID) or data.subjectID < 1 then return end
  local vehicle = findVehicleById(data.subjectID)
  if not vehicle then return end
  local vehicleId = vehicle:getId()
  if vehicleId ~= data.subjectID then return end

  local occupied = record.occupancy[vehicleId] == true
  if data.event == "enter" and occupied then return end
  if data.event == "exit" and not occupied then return end
  record.occupancy[vehicleId] = data.event == "enter" or nil

  -- Occupancy is lifecycle state, not action state. Always update it before
  -- applying the selected event subset so exit-only and enter-only actions can
  -- re-arm correctly.
  if not record.action.event_set[data.event] then return end

  if realElapsedSeconds - record.rate_window_started >= 1 then
    record.rate_window_started = realElapsedSeconds
    record.rate_count = 0
  end
  if record.rate_count >= MAX_TRIGGER_EVENTS_PER_SECOND then return end
  record.rate_count = record.rate_count + 1
  record.sequence = record.sequence + 1
  record.count = record.count + 1
  local subjectName = vehicle:getName()
  if type(subjectName) ~= "string" or #subjectName < 1 then
    subjectName = "vehicle_" .. tostring(vehicleId)
  end
  if #subjectName > MAX_IDENTIFIER_LENGTH then
    subjectName = subjectName:sub(1, MAX_IDENTIFIER_LENGTH)
  end
  record.last_event = {
    sequence = record.sequence,
    event = data.event,
    subject_id = vehicleId,
    subject_name = subjectName,
    time_seconds = realElapsedSeconds
  }
  sendEnvelope(record.owner, eventEnvelope("trigger.event", {
    handle = record.handle,
    event = data.event,
    subject_id = vehicleId,
    subject_name = subjectName,
    trigger_id = record.object_id,
    trigger_name = record.name,
    sequence = record.sequence,
    count = record.count,
    time_seconds = realElapsedSeconds
  }))
end

local function stopLeaseVehicles(lease)
  local stopped = {}
  if lease.vehicle_id ~= nil then
    local vehicle = findVehicleById(lease.vehicle_id)
    if vehicle then table.insert(stopped, stopVehicle(vehicle)) end
  else
    for _, vehicle in ipairs(getAllVehicles()) do
      table.insert(stopped, stopVehicle(vehicle))
    end
  end
  return stopped
end

local function expireSafetyLease(reason)
  if not safetyLease then return {} end
  local expired = safetyLease
  safetyLease = nil
  local stopped = stopLeaseVehicles(expired)
  broadcastAuthenticated(eventEnvelope("safety.lease_expired", {
    reason = reason,
    lease_id = expired.lease_id,
    vehicle_ids = stopped
  }))
  return stopped
end

HANDLERS["safety.lease_arm"] = function(params)
  if not validRequestId(params.lease_id) then
    return nil, protocolError("invalid_lease", "lease_id must be a safe non-empty string")
  end
  if safetyLease then
    return nil, protocolError("lease_already_armed", "a safety lease is already armed")
  end
  if params.vehicle_id ~= nil and params.vehicle_name ~= nil then
    return nil, protocolError("invalid_vehicle", "provide vehicle_id or vehicle_name, not both")
  end
  local target = nil
  if params.vehicle_id ~= nil then
    if not isInteger(params.vehicle_id) or params.vehicle_id < 1 then
      return nil, protocolError("invalid_vehicle", "vehicle_id must be a positive integer")
    end
    target = findVehicleById(params.vehicle_id)
  elseif params.vehicle_name ~= nil then
    if not validIdentifier(params.vehicle_name) then
      return nil, protocolError("invalid_vehicle", "vehicle_name must be a safe identifier")
    end
    target = findVehicleByName(params.vehicle_name)
  else
    return nil, protocolError("invalid_vehicle", "vehicle_id or vehicle_name is required")
  end
  if not target then
    return nil, protocolError("vehicle_not_found", "vehicle was not found")
  end
  safetyLease = {
    lease_id = params.lease_id,
    vehicle_id = target:getId(),
    vehicle_name = target:getName(),
    expires_at = realElapsedSeconds + config.safety_startup_grace_seconds
  }
  return {
    armed = true,
    lease_id = safetyLease.lease_id,
    vehicle_id = safetyLease.vehicle_id,
    vehicle_name = safetyLease.vehicle_name,
    lease_seconds = config.safety_lease_seconds,
    expires_in_seconds = config.safety_startup_grace_seconds
  }, nil
end

HANDLERS["safety.lease_renew"] = function(params)
  if safetyLease and realElapsedSeconds >= safetyLease.expires_at then
    expireSafetyLease("lease_expired")
  end
  if not safetyLease then
    return nil, protocolError("lease_not_armed", "no safety lease is armed")
  end
  if params.lease_id ~= safetyLease.lease_id then
    return nil, protocolError("lease_mismatch", "lease_id does not match the armed lease")
  end
  safetyLease.expires_at = realElapsedSeconds + config.safety_lease_seconds
  return {
    armed = true,
    lease_id = safetyLease.lease_id,
    expires_in_seconds = config.safety_lease_seconds
  }, nil
end

HANDLERS["safety.lease_disarm"] = function(params)
  if not safetyLease then return {disarmed = false, armed = false}, nil end
  if params.lease_id ~= safetyLease.lease_id then
    return nil, protocolError("lease_mismatch", "lease_id does not match the armed lease")
  end
  local leaseId = safetyLease.lease_id
  safetyLease = nil
  broadcastAuthenticated(eventEnvelope("safety.lease_disarmed", {lease_id = leaseId}))
  return {disarmed = true, armed = false, lease_id = leaseId}, nil
end

HANDLERS["emergency_stop"] = function(params)
  local stopped = {}
  if params.vehicle_id ~= nil and params.vehicle_name ~= nil then
    return nil, protocolError("invalid_vehicle", "provide vehicle_id or vehicle_name, not both")
  end
  if params.vehicle_id ~= nil then
    if not isInteger(params.vehicle_id) or params.vehicle_id < 1 then
      return nil, protocolError("invalid_vehicle", "vehicle_id must be a positive integer")
    end
    local target = nil
    for _, vehicle in ipairs(getAllVehicles()) do
      if vehicle:getId() == params.vehicle_id then
        target = vehicle
        break
      end
    end
    if not target then return nil, protocolError("vehicle_not_found", "vehicle was not found") end
    table.insert(stopped, stopVehicle(target))
  elseif params.vehicle_name ~= nil then
    if not validIdentifier(params.vehicle_name) then
      return nil, protocolError("invalid_vehicle", "vehicle_name must be a safe identifier")
    end
    local target = findVehicleByName(params.vehicle_name)
    if not target then return nil, protocolError("vehicle_not_found", "vehicle was not found") end
    table.insert(stopped, stopVehicle(target))
  else
    for _, vehicle in ipairs(getAllVehicles()) do
      table.insert(stopped, stopVehicle(vehicle))
    end
  end

  broadcastAuthenticated(eventEnvelope("safety.emergency_stop", {vehicle_ids = stopped}))
  return {stopped = true, vehicle_ids = stopped}, nil
end

local function revokePeerAuthentication(peerId, peer, reason)
  -- Always clean ownership, even when the peer already appears unauthenticated.
  -- This keeps malformed/missing-token requests fail-closed if peer state and
  -- trigger ownership ever diverge.
  cleanupTriggersForPeer(peerId, reason)
  peer.authenticated = false
end

local function boundedAuthenticationRequest(request)
  return {
    id = validRequestId(request and request.id) and request.id or "protocol-error",
    method = "protocol.authentication"
  }
end

local function validateRequest(request)
  if type(request) ~= "table" then
    return protocolError("invalid_request", "request must be a JSON object")
  end
  for key, _ in pairs(request) do
    if not REQUEST_KEYS[key] then
      return protocolError("invalid_request", "request contains an unknown envelope field")
    end
  end
  if request.schema ~= SCHEMA_VERSION then
    return protocolError("unsupported_schema", "schema must be 1")
  end
  if not validRequestId(request.id) then
    return protocolError("invalid_request_id", "id must be a safe non-empty string")
  end
  if request.type ~= "request" then
    return protocolError("invalid_type", "type must be request")
  end
  if type(request.method) ~= "string" or not HANDLERS[request.method] then
    return protocolError("unknown_method", "method is not in the command allowlist")
  end
  if request.params == nil then request.params = {} end
  if type(request.params) ~= "table" then
    return protocolError("invalid_params", "params must be a JSON object")
  end
  if type(request.token) ~= "string" then
    return protocolError("authentication_failed", "a token is required")
  end
  return nil
end

local function handleMessage(peerId, message)
  local peer = peers[peerId]
  if not peer then
    peer = {authenticated = false, last_seen = elapsedSeconds, failures = 0}
    peers[peerId] = peer
  end

  if type(message) ~= "string" or #message == 0 then return end
  if #message > config.max_payload_bytes then
    peer.failures = peer.failures + 1
    sendError(peerId, nil, "payload_too_large", "message exceeds max_payload_bytes")
    return
  end

  local decodedOk, request = pcall(jsonDecode, message)
  if not decodedOk or type(request) ~= "table" then
    peer.failures = peer.failures + 1
    sendError(peerId, nil, "invalid_json", "message must contain valid JSON")
    return
  end

  -- Authenticate before generic envelope validation. Otherwise a peer that
  -- was already authenticated could combine a missing/wrong token with an
  -- earlier schema or method error and avoid credential revocation.
  if type(request.token) ~= "string"
    or not constantTimeEquals(request.token, config.token) then
    revokePeerAuthentication(peerId, peer, "authentication_failed")
    peer.failures = peer.failures + 1
    sendError(
      peerId,
      boundedAuthenticationRequest(request),
      "authentication_failed",
      "token was rejected"
    )
    return
  end

  local requestError = validateRequest(request)
  if requestError then
    if requestError.code == "authentication_failed" then
      revokePeerAuthentication(peerId, peer, "authentication_failed")
    end
    peer.failures = peer.failures + 1
    sendEnvelope(peerId, responseEnvelope(request, nil, requestError))
    return
  end

  peer.authenticated = true
  peer.last_seen = elapsedSeconds
  peer.failures = 0

  local handler = HANDLERS[request.method]
  local callOk, result, handlerError = pcall(handler, request.params, peerId, request)
  if not callOk then
    log("E", LOG_TAG, "Handler failed for " .. request.method .. ": " .. tostring(result))
    sendError(peerId, request, "internal_error", "command handler failed")
    return
  end
  if handlerError then
    sendEnvelope(peerId, responseEnvelope(request, nil, handlerError))
    return
  end
  sendEnvelope(peerId, responseEnvelope(request, result, nil))
end

local function expireStaleAuthentication()
  for peerId, peer in pairs(peers) do
    if peer.authenticated
      and elapsedSeconds - peer.last_seen > config.heartbeat_timeout_seconds then
      cleanupTriggersForPeer(peerId, "authentication_expired")
      peer.authenticated = false
    end
  end
end

local function startWebSocketServer()
  if server or not config then return server ~= nil end
  local createOk, createdServer, chosenAddress = pcall(
    wsUtils.createOrGetWS,
    LOOPBACK_ADDRESS,
    config.port,
    WEBSOCKET_PATH,
    WEBSOCKET_PROTOCOL,
    "",
    false
  )
  if not createOk or not createdServer then
    log("E", LOG_TAG, "Unable to start the loopback WebSocket server")
    server = nil
    return false
  end
  server = createdServer
  log(
    "I",
    LOG_TAG,
    "BeamNG MCP bridge listening on " .. tostring(chosenAddress) .. ":" .. tostring(config.port)
  )
  return true
end

local function onExtensionLoaded()
  local resolved, configError = readConfig()
  if configError then
    log("E", LOG_TAG, "Bridge disabled: " .. configError)
    return
  end
  config = resolved
  restartServerRequested = false

  if setExtensionUnloadMode then setExtensionUnloadMode(M, "manual") end
  startWebSocketServer()
end

local function onExtensionUnloaded()
  if safetyLease then expireSafetyLease("extension_unloaded") end
  cleanupAllTriggers("extension_unloaded")
  if server then
    pcall(BNGWebWSServer.destroy, server)
    server = nil
  end
  peers = {}
  restartServerRequested = false
  managedObjects = {}
  pendingReload = nil
  log("I", LOG_TAG, "BeamNG MCP bridge stopped")
end

local function resetWebSocketServer(reason)
  if safetyLease then expireSafetyLease(reason) end
  cleanupAllTriggers(reason)
  if server then
    pcall(BNGWebWSServer.destroy, server)
    server = nil
  end
  peers = {}
  restartServerRequested = true
end

local function resetOverloadedServer(eventCount, dataBytes)
  resetWebSocketServer("bridge_event_overload")
  log(
    "W",
    LOG_TAG,
    "Resetting overloaded WebSocket server before processing batch: events="
      .. tostring(eventCount)
      .. ", data_bytes="
      .. tostring(dataBytes)
  )
end

local function onClientStartMission()
  resetWebSocketServer("mission_started")
  releaseGoneQuarantinedTriggers("mission_started")
  managedObjects = {}
end

local function onClientEndMission()
  resetWebSocketServer("mission_ended")
  releaseGoneQuarantinedTriggers("mission_ended")
  managedObjects = {}
end

local function onUpdate(dtReal, dtSim, dtRaw)
  local delta = dtReal or dtSim or dtRaw or 0
  if not isFiniteNumber(delta) or delta < 0 then delta = 0 end
  local realDelta = dtReal or 0
  if not isFiniteNumber(realDelta) or realDelta < 0 then realDelta = 0 end
  elapsedSeconds = elapsedSeconds + delta
  realElapsedSeconds = realElapsedSeconds + realDelta
  telemetryElapsed = telemetryElapsed + delta
  heartbeatElapsed = heartbeatElapsed + delta

  if safetyLease and realElapsedSeconds >= safetyLease.expires_at then
    expireSafetyLease("lease_expired")
  end

  if not config then return end
  if not server then
    if restartServerRequested and startWebSocketServer() then
      restartServerRequested = false
    end
    return
  end

  local eventsOk, events = pcall(function() return server:getPeerEvents() end)
  if eventsOk and type(events) == "table" then
    if #events > MAX_EVENTS_PER_UPDATE then
      resetOverloadedServer(#events, 0)
      return
    end
    local dataBytes = 0
    for _, event in ipairs(events) do
      if event.type == "D" and type(event.msg) == "string" then
        dataBytes = dataBytes + #event.msg
      end
    end
    local byteLimit = math.min(MAX_DATA_BYTES_PER_UPDATE, config.max_payload_bytes * 4)
    if dataBytes > byteLimit then
      resetOverloadedServer(#events, dataBytes)
      return
    end

    for _, event in ipairs(events) do
      if event.type == "C" then
        cleanupTriggersForPeer(event.peerId, "peer_reconnected")
        peers[event.peerId] = {
          authenticated = false,
          last_seen = elapsedSeconds,
          failures = 0
        }
      elseif event.type == "DC" then
        cleanupTriggersForPeer(event.peerId, "peer_disconnected")
        peers[event.peerId] = nil
      elseif event.type == "D" and event.msg ~= "" then
        handleMessage(event.peerId, event.msg)
      end
    end
  end

  if telemetryElapsed >= config.telemetry_interval_seconds then
    telemetryElapsed = 0
    local snapshotOk, snapshot = pcall(telemetrySnapshot)
    if snapshotOk then
      broadcastAuthenticated(eventEnvelope("telemetry.snapshot", snapshot))
    end
  end

  if heartbeatElapsed >= config.heartbeat_interval_seconds then
    heartbeatElapsed = 0
    expireStaleAuthentication()
    broadcastAuthenticated(eventEnvelope("heartbeat", {time_seconds = elapsedSeconds}))
  end

  pcall(function() server:update() end)

  if pendingReload then
    local extensionName = pendingReload
    pendingReload = nil
    if next(managedTriggers) ~= nil or next(managedObjects) ~= nil then
      log(
        "W",
        LOG_TAG,
        "Cancelled bridge extension reload because managed scene state appeared after scheduling"
      )
    else
      extensions.reload(extensionName)
    end
  end
end

M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded
M.onClientStartMission = onClientStartMission
M.onClientEndMission = onClientEndMission
M.onBeamNGTrigger = onBeamNGTrigger
M.onUpdate = onUpdate

return M
