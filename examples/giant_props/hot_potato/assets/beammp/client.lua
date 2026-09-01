-- Hot Potato BeamMP transport adapter.
--
-- The server relay and the Sumo Rink use the same two event names and
-- envelope. This file deliberately knows no game rules: the prop-owned
-- runtime remains the authority in single-player and, when elected by the
-- relay, on the BeamMP client that owns the prop vehicle.

local M = {}

local C2S_EVENT = "ericrolph_games_c2s_v1"
local S2C_EVENT = "ericrolph_games_s2c_v1"
local HANDLER_NAME = "ericrolph_hot_potato_s2c_v1"
local GAME = "hot_potato"
local PROTOCOL = 1
local HELLO_SECONDS = 2.0

local records = {}
local elapsed = 0
local handlerInstalled = false

local function runtime()
  return extensions and extensions.ericrolph__hot__potato_runtime or nil
end

local function notifyRuntime(packet)
  local target = runtime()
  if not target or type(target.hotPotatoBeamMPReceive) ~= "function" then return false end
  local ok = pcall(target.hotPotatoBeamMPReceive, packet)
  return ok
end

local function notifyTransport(connected, arena, reason, gameId)
  local target = runtime()
  if not target or type(target.hotPotatoBeamMPTransport) ~= "function" then return false end
  local ok = pcall(target.hotPotatoBeamMPTransport, {
    connected = connected == true,
    arena = arena,
    reason = reason,
    game_id = gameId,
  })
  return ok
end

local function network()
  return extensions and extensions.MPCoreNetwork or rawget(_G, "MPCoreNetwork")
end

local function isMPSession()
  local api = network()
  if not api or type(api.isMPSession) ~= "function" then return false end
  local ok, active = pcall(api.isMPSession)
  return ok and active == true
end

local function vehicleApi()
  return extensions and extensions.MPVehicleGE or rawget(_G, "MPVehicleGE")
end

local function serverVehicleId(gameId)
  local api = vehicleApi()
  if not api or type(api.getServerVehicleID) ~= "function" then return nil end
  local ok, sid = pcall(api.getServerVehicleID, gameId)
  if ok and type(sid) == "string" and sid:match("^%d+%-%d+$") then return sid end
  return nil
end

local function isOwn(gameId)
  local api = vehicleApi()
  if not api or type(api.isOwn) ~= "function" then return false end
  local ok, own = pcall(api.isOwn, gameId)
  return ok and own == true
end

local function encode(value)
  if type(jsonEncode) ~= "function" then return nil end
  local ok, result = pcall(jsonEncode, value)
  if ok and type(result) == "string" then return result end
  return nil
end

local function decode(value)
  if type(value) == "table" then return value end
  if type(value) ~= "string" or #value > 262144 then return nil end
  if type(jsonDecode) ~= "function" then return nil end
  local ok, result = pcall(jsonDecode, value)
  if ok and type(result) == "table" then return result end
  return nil
end

local function send(record, kind, body)
  if not isMPSession() or type(TriggerServerEvent) ~= "function" then return false end
  if type(record.arena) ~= "string" or record.arena == "" then return false end
  record.seq = (record.seq or 0) + 1
  local envelope = {
    v = PROTOCOL,
    game = GAME,
    arena = record.arena,
    kind = kind,
    epoch = record.epoch or 0,
    seq = record.seq,
    revision = record.revision or 0,
    body = body or {},
  }
  local payload = encode(envelope)
  if not payload or #payload > 262144 then return false end
  local ok = pcall(TriggerServerEvent, C2S_EVENT, payload)
  return ok
end

local function hello(record)
  record.lastHello = elapsed
  return send(record, "hello", {
    prop_sid = record.arena,
    owner = isOwn(record.gameId),
  })
end

local function matchingRecords(arena)
  local result = {}
  for _, record in pairs(records) do
    if record.arena == arena then result[#result + 1] = record end
  end
  return result
end

local function receive(raw)
  local packet = decode(raw)
  if not packet
    or packet.v ~= PROTOCOL
    or packet.game ~= GAME
    or type(packet.arena) ~= "string"
    or type(packet.kind) ~= "string" then
    return
  end
  if packet.kind ~= "role" and packet.kind ~= "state"
    and packet.kind ~= "command" and packet.kind ~= "closed"
    and packet.kind ~= "reject" then
    return
  end
  packet.body = packet.body or packet.payload or {}
  if type(packet.body) ~= "table" then return end
  local serverSeq = tonumber(packet.seq)
  if not serverSeq or serverSeq < 0 or serverSeq ~= math.floor(serverSeq) then return end
  local epoch = packet.epoch
  if epoch ~= nil and (type(epoch) ~= "number" or epoch < 0
    or epoch ~= math.floor(epoch)) then return end
  for _, record in ipairs(matchingRecords(packet.arena)) do
    local revision = tonumber(packet.revision) or 0
    local terminal = packet.kind == "closed" or packet.kind == "reject"
    -- S2C seq is delivery order across kinds; state revision may legitimately
    -- go backwards when a late join gets a role followed by cached state.
    -- Reset terminals additionally bypass seq because a new epoch restarts it.
    if terminal or serverSeq > (record.serverSeq or 0) then
      record.serverSeq = serverSeq
      if terminal then
        record.revision = 0
      else
        record.revision = revision
      end
      if packet.epoch ~= nil then record.epoch = packet.epoch end
      if packet.kind == "role" then
        local role = packet.body.role
        if role ~= "authority" and role ~= "follower" then
          role = packet.body.authority == true and "authority" or "follower"
        end
        record.role = role
      elseif packet.kind == "closed" or packet.kind == "reject" then
        record.role = "pending"
        record.lastHello = elapsed
      end
      notifyRuntime(packet)
    end
  end
end

function M.registerProp(gameId)
  gameId = tonumber(gameId)
  if not gameId then return false end
  local record = records[gameId]
  if not record then
    record = {
      gameId = gameId,
      seq = 0,
      serverSeq = 0,
      revision = 0,
      role = "pending",
      wasMP = isMPSession(),
    }
    records[gameId] = record
  end
  record.arena = serverVehicleId(gameId) or record.arena
  if record.wasMP and record.arena then hello(record) end
  return true
end

function M.unregisterProp(gameId)
  gameId = tonumber(gameId)
  if not gameId then return false end
  records[gameId] = nil
  return true
end

function M.publishState(gameId, snapshot)
  local record = records[tonumber(gameId)]
  if not record or record.role ~= "authority" or type(snapshot) ~= "table" then return false end
  return send(record, "state", snapshot)
end

function M.publishCommand(gameId, command)
  local record = records[tonumber(gameId)]
  if not record or record.role ~= "authority" or type(command) ~= "table" then return false end
  return send(record, "command", command)
end

function M.requestResync(gameId)
  local record = records[tonumber(gameId)]
  if not record then return false end
  return send(record, "resync", {last_revision = record.revision or 0})
end

function M.onUpdate(dtReal)
  elapsed = elapsed + math.max(0, tonumber(dtReal) or 0)
  local active = isMPSession()
  for _, record in pairs(records) do
    if record.wasMP ~= active then
      record.wasMP = active
      record.role = active and "pending" or "standalone"
      record.epoch = nil
      record.revision = 0
      record.seq = 0
      record.serverSeq = 0
      record.lastHello = nil
      notifyTransport(active, record.arena, active and "joined" or "left",
        record.gameId)
    end
    if active then
      local arena = serverVehicleId(record.gameId)
      if arena and arena ~= record.arena then
        record.arena = arena
        record.role = "pending"
        record.epoch = nil
        record.revision = 0
        record.seq = 0
        record.serverSeq = 0
        record.lastHello = nil
        notifyTransport(true, arena, "mapped", record.gameId)
      end
      if record.arena and record.role == "pending"
        and (record.lastHello == nil or elapsed - record.lastHello >= HELLO_SECONDS) then
        hello(record)
      end
    end
  end
end

function M.onBeamMPServerLeave()
  for _, record in pairs(records) do
    record.wasMP = false
    record.role = "standalone"
    record.epoch = nil
    record.revision = 0
    record.serverSeq = 0
    notifyTransport(false, record.arena, "server_leave", record.gameId)
  end
end

function M.onBeamMPPostJoin()
  for _, record in pairs(records) do
    record.wasMP = true
    record.role = "pending"
    record.epoch = nil
    record.revision = 0
    record.seq = 0
    record.serverSeq = 0
    record.lastHello = nil
    record.arena = serverVehicleId(record.gameId) or record.arena
    notifyTransport(true, record.arena, "post_join", record.gameId)
    if record.arena then hello(record) end
  end
end

function M.onClientEndMission()
  records = {}
end

function M.onExtensionLoaded()
  if type(setExtensionUnloadMode) == "function" then
    setExtensionUnloadMode(M, "manual")
  end
  if type(AddEventHandler) == "function" and not handlerInstalled then
    AddEventHandler(S2C_EVENT, receive, HANDLER_NAME)
    handlerInstalled = true
  end
end

M.onInit = M.onExtensionLoaded

function M.onExtensionUnloaded()
  if type(RemoveEventHandler) == "function" and handlerInstalled then
    pcall(RemoveEventHandler, S2C_EVENT, HANDLER_NAME)
  end
  handlerInstalled = false
  records = {}
end

return M
