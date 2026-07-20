-- BeamNG MCP GELua bridge.
--
-- This extension deliberately exposes a small, typed command surface. It does
-- not run client-provided Lua or accept arbitrary object fields/classes.

local M = {}

M.dependencies = {"core_gamestate"}

local LOG_TAG = "beamng_mcp_bridge"
local BRIDGE_VERSION = "0.2.0"
local SCHEMA_VERSION = 1
local LOOPBACK_ADDRESS = "127.0.0.1"
local WEBSOCKET_PATH = ""
local WEBSOCKET_PROTOCOL = "beamng-mcp-v1"
local CONFIG_PATH = "/settings/beamng_mcp.json"
local CONFIG_MARKER = "beamng-mcp-bridge"
local TOKEN_PLACEHOLDER = "__BEAMNG_MCP_TOKEN__"

local HARD_MAX_PAYLOAD_BYTES = 1048576
local MAX_EVENTS_PER_UPDATE = 64
local MAX_OBJECT_RESULTS = 200
local MAX_IDENTIFIER_LENGTH = 96

local wsUtils = require("utils/wsUtils")

local server = nil
local config = nil
local peers = {}
local managedObjects = {}
local elapsedSeconds = 0
local realElapsedSeconds = 0
local telemetryElapsed = 0
local heartbeatElapsed = 0
local pendingReload = nil
local safetyLease = nil

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

local function objectDescriptor(object, includeFields)
  local className = object:getClassName()
  local descriptor = {
    id = object:getId(),
    name = object:getName(),
    class = className,
    managed = managedObjects[object:getId()] == true
  }

  local positionOk, position = pcall(function() return object:getPosition() end)
  if positionOk then descriptor.position = vectorToTable(position) end

  local rotationOk, rotation = pcall(function() return quat(object:getRotation()) end)
  if rotationOk then descriptor.rotation = quaternionToTable(rotation) end

  local scaleOk, scale = pcall(function() return object:getScale() end)
  if scaleOk then descriptor.scale = vectorToTable(scale) end

  if includeFields then
    descriptor.fields = {}
    for fieldName, _ in pairs(FIELD_RULES[className] or {}) do
      local fieldOk, fieldValue = pcall(function() return object:getField(fieldName, 0) end)
      if fieldOk then descriptor.fields[fieldName] = fieldValue end
    end
  end
  return descriptor
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
  if requestedClass ~= nil and not CREATABLE_CLASSES[requestedClass] then
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
      if CREATABLE_CLASSES[className]
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
  local _, writableError = ensureWritableObject(object)
  if writableError then return nil, protocolError("object_unavailable", writableError) end
  return objectDescriptor(object, true), nil
end

HANDLERS["world.create_object"] = function(params)
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

  managedObjects[object:getId()] = true
  markEditorDirty()
  return objectDescriptor(object, true), nil
end

local function ensureManagedMutation(object)
  if managedObjects[object:getId()] == true or config.allow_existing_map_object_edits then
    return true, nil
  end
  return nil, "existing map object edits are disabled by configuration"
end

HANDLERS["world.update_object"] = function(params)
  local object, resolveError = resolveObject(params)
  if resolveError then return nil, protocolError("invalid_identifier", resolveError) end
  local className, writableError = ensureWritableObject(object)
  if writableError then return nil, protocolError("object_unavailable", writableError) end
  local _, managedError = ensureManagedMutation(object)
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
  markEditorDirty()
  return objectDescriptor(object, true), nil
end

HANDLERS["world.delete_object"] = function(params)
  if params.confirm ~= true then
    return nil, protocolError("confirmation_required", "set confirm to true to delete an object")
  end
  local object, resolveError = resolveObject(params)
  if resolveError then return nil, protocolError("invalid_identifier", resolveError) end
  local _, writableError = ensureWritableObject(object)
  if writableError then return nil, protocolError("object_unavailable", writableError) end
  local _, managedError = ensureManagedMutation(object)
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
  managedObjects[objectId] = nil
  markEditorDirty()
  return {deleted = true, id = objectId, name = objectName}, nil
end

HANDLERS["world.save_level"] = function(params)
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
  local extensionName = params.name or "beamng_mcp/bridge"
  local canonicalName = type(extensionName) == "string"
    and RELOADABLE_EXTENSIONS[extensionName]
    or nil
  if not canonicalName then
    return nil, protocolError("extension_not_allowed", "extension is not in the reload allowlist")
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

  local requestError = validateRequest(request)
  if requestError then
    peer.failures = peer.failures + 1
    sendEnvelope(peerId, responseEnvelope(request, nil, requestError))
    return
  end

  if not constantTimeEquals(request.token, config.token) then
    peer.authenticated = false
    peer.failures = peer.failures + 1
    sendError(peerId, request, "authentication_failed", "token was rejected")
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
  for _, peer in pairs(peers) do
    if peer.authenticated
      and elapsedSeconds - peer.last_seen > config.heartbeat_timeout_seconds then
      peer.authenticated = false
    end
  end
end

local function onExtensionLoaded()
  local resolved, configError = readConfig()
  if configError then
    log("E", LOG_TAG, "Bridge disabled: " .. configError)
    return
  end
  config = resolved

  if setExtensionUnloadMode then setExtensionUnloadMode(M, "manual") end

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
    return
  end
  server = createdServer
  log(
    "I",
    LOG_TAG,
    "BeamNG MCP bridge listening on " .. tostring(chosenAddress) .. ":" .. tostring(config.port)
  )
end

local function onExtensionUnloaded()
  if safetyLease then expireSafetyLease("extension_unloaded") end
  if server then
    pcall(BNGWebWSServer.destroy, server)
    server = nil
  end
  peers = {}
  managedObjects = {}
  pendingReload = nil
  log("I", LOG_TAG, "BeamNG MCP bridge stopped")
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

  if not server or not config then return end

  local eventsOk, events = pcall(function() return server:getPeerEvents() end)
  if eventsOk and type(events) == "table" then
    local processed = 0
    for _, event in ipairs(events) do
      if processed >= MAX_EVENTS_PER_UPDATE then break end
      processed = processed + 1
      if event.type == "C" then
        peers[event.peerId] = {
          authenticated = false,
          last_seen = elapsedSeconds,
          failures = 0
        }
      elseif event.type == "DC" then
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
    extensions.reload(extensionName)
  end
end

M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded
M.onUpdate = onUpdate

return M
