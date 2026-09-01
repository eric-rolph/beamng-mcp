-- Authoritative BeamMP relay for the EricRolph Hot Potato and Sumo props.
--
-- The owning client of each prop (the PID prefix in its canonical BeamMP
-- vehicle id) is the sole gameplay authority.  This resource validates and
-- stamps messages, caches the latest snapshot for late joiners, and never
-- attempts to simulate either game on the server.

local PROTOCOL_VERSION = 1
local C2S_EVENT = "ericrolph_games_c2s_v1"
local S2C_EVENT = "ericrolph_games_s2c_v1"
local MAX_RAW_BYTES = 64 * 1024
local MAX_SAFE_EPOCH = 9007199254740991

local VALID_GAMES = {hot_potato = true, sumo = true}
local VALID_KINDS = {
  hello = true,
  state = true,
  command = true,
  resync = true,
  intent = true,
  heartbeat = true,
}

-- Keyed by game .. NUL .. canonical prop SID.  A sequence is tracked per
-- sender because followers can send intents independently of the authority.
local sessions = {}
local rejectionSeq = {}
local registered = false

local function isInteger(value)
  return type(value) == "number"
    and value == value
    and value ~= math.huge
    and value ~= -math.huge
    and value == math.floor(value)
end

local function normalizePid(value)
  if type(value) == "string" and value:match("^%d+$") then
    value = tonumber(value)
  end
  if not isInteger(value) or value < 0 then return nil end
  return value
end

local function sessionKey(game, arena)
  return game .. "\0" .. arena
end

local function safeSend(playerID, envelope)
  if not MP or type(MP.TriggerClientEventJson) ~= "function" then return false end
  local ok = pcall(MP.TriggerClientEventJson, playerID, S2C_EVENT, envelope)
  return ok
end

local function envelopeFor(session, kind, body, senderPid, revision)
  session.outSeq = (session.outSeq or 0) + 1
  local envelope = {
    v = PROTOCOL_VERSION,
    game = session.game,
    arena = session.arena,
    kind = kind,
    epoch = session.epoch,
    seq = session.outSeq,
    revision = revision or session.revision,
    body = body or {},
  }
  if senderPid ~= nil then envelope.senderPid = senderPid end
  return envelope
end

local function reject(playerID, code, message, parsed, session)
  if not session and type(parsed) == "table"
      and VALID_GAMES[parsed.game]
      and type(parsed.arena) == "string"
      and parsed.arena:match("^%d+%-%d+$") then
    session = sessions[sessionKey(parsed.game, parsed.arena)]
  end
  local body = {code = code, message = message}
  local envelope
  if session then
    envelope = envelopeFor(session, "reject", body)
  else
    local normalized = normalizePid(playerID)
    local sequenceKey = normalized or tostring(playerID)
    rejectionSeq[sequenceKey] = (rejectionSeq[sequenceKey] or 0) + 1
    envelope = {
      v = PROTOCOL_VERSION,
      kind = "reject",
      seq = rejectionSeq[sequenceKey],
      body = body,
    }
  end
  if not session and type(parsed) == "table" then
    if VALID_GAMES[parsed.game] then envelope.game = parsed.game end
    if type(parsed.arena) == "string" and parsed.arena:match("^%d+%-%d+$") then
      envelope.arena = parsed.arena
    end
    if isInteger(parsed.epoch) and parsed.epoch >= 0 then
      envelope.epoch = parsed.epoch
    end
  end
  safeSend(playerID, envelope)
  return false
end

local function decodeAndValidate(playerID, raw)
  if type(raw) ~= "string" then
    reject(playerID, "invalid_raw", "event data must be a JSON string")
    return nil
  end
  if #raw > MAX_RAW_BYTES then
    reject(playerID, "message_too_large", "event data exceeds 64 KiB")
    return nil
  end
  if not Util or type(Util.JsonDecode) ~= "function" then
    reject(playerID, "server_error", "JSON decoder is unavailable")
    return nil
  end

  local ok, message = pcall(Util.JsonDecode, raw)
  if not ok or type(message) ~= "table" then
    reject(playerID, "invalid_json", "event data is not a JSON object")
    return nil
  end
  if message.v ~= PROTOCOL_VERSION then
    reject(playerID, "unsupported_version", "protocol version must be 1", message)
    return nil
  end
  if type(message.game) ~= "string" or not VALID_GAMES[message.game] then
    reject(playerID, "invalid_game", "game must be hot_potato or sumo", message)
    return nil
  end
  if type(message.arena) ~= "string"
      or not message.arena:match("^%d+%-%d+$") then
    reject(playerID, "invalid_arena", "arena must be a canonical PID-VID", message)
    return nil
  end
  if type(message.kind) ~= "string" or not VALID_KINDS[message.kind] then
    reject(playerID, "invalid_kind", "unsupported client message kind", message)
    return nil
  end
  if not isInteger(message.seq) or message.seq < 0 then
    reject(playerID, "invalid_seq", "seq must be a non-negative integer", message)
    return nil
  end
  if message.epoch ~= nil
      and (not isInteger(message.epoch) or message.epoch < 0) then
    reject(playerID, "invalid_epoch", "epoch must be a non-negative integer", message)
    return nil
  end
  if message.revision ~= nil
      and (not isInteger(message.revision) or message.revision < 0) then
    reject(playerID, "invalid_revision", "revision must be a non-negative integer", message)
    return nil
  end

  local senderPid = normalizePid(playerID)
  if senderPid == nil then
    reject(playerID, "invalid_sender", "BeamMP supplied an invalid player id", message)
    return nil
  end
  -- A sender id is always injected from BeamMP.  Optional client-supplied
  -- aliases are accepted only when they agree, preventing identity spoofing.
  for _, field in ipairs({"senderPid", "sender"}) do
    if message[field] ~= nil then
      local claimed = normalizePid(message[field])
      if claimed == nil or claimed ~= senderPid then
        reject(playerID, "sender_mismatch", "client sender does not match BeamMP", message)
        return nil
      end
    end
  end

  local ownerText = message.arena:match("^(%d+)%-%d+$")
  local hostPid = normalizePid(ownerText)
  if hostPid == nil then
    reject(playerID, "invalid_arena", "arena owner is outside the player-id range", message)
    return nil
  end

  local body = message.body
  if body == nil then body = message.payload end -- tolerate pre-v1 adapters
  if body == nil then body = {} end
  if type(body) ~= "table" then
    reject(playerID, "invalid_body", "body must be a JSON object or array", message)
    return nil
  end

  return {
    raw = message,
    game = message.game,
    arena = message.arena,
    kind = message.kind,
    seq = message.seq,
    epoch = message.epoch,
    revision = message.revision,
    body = body,
    senderPid = senderPid,
    hostPid = hostPid,
  }
end

local function newSession(parsed)
  local session = {
    game = parsed.game,
    arena = parsed.arena,
    hostPid = parsed.hostPid,
    epoch = 1,
    lastSeq = {},
    revision = 0,
    latestState = nil,
    latestStateRevision = nil,
    ready = false,
    outSeq = 0,
  }
  sessions[sessionKey(parsed.game, parsed.arena)] = session
  return session
end

local function sendRole(session, playerID)
  local authority = playerID == session.hostPid
  safeSend(playerID, envelopeFor(session, "role", {
    role = authority and "authority" or "follower",
    authority = authority,
    hostPid = session.hostPid,
    ready = session.ready,
  }))
end

local function sendCachedState(session, playerID)
  if session.latestState == nil then return end
  safeSend(playerID, envelopeFor(
    session,
    "state",
    session.latestState,
    session.hostPid,
    session.latestStateRevision))
end

local function sequenceIsFresh(session, parsed)
  local previous = session.lastSeq[parsed.senderPid]
  if previous ~= nil and parsed.seq <= previous then
    return reject(
      parsed.senderPid,
      "stale_seq",
      "seq must increase for each sender",
      parsed.raw,
      session)
  end
  return true
end

local function epochMatches(session, parsed)
  if parsed.epoch ~= session.epoch then
    return reject(
      parsed.senderPid,
      "stale_epoch",
      "message epoch does not match the active session",
      parsed.raw,
      session)
  end
  return true
end

local function acceptSequence(session, parsed)
  session.lastSeq[parsed.senderPid] = parsed.seq
end

local function broadcast(session, kind, body, senderPid, revision)
  safeSend(-1, envelopeFor(session, kind, body, senderPid, revision))
end

function ericrolphGamesOnClientEvent(playerID, raw)
  local parsed = decodeAndValidate(playerID, raw)
  if not parsed then return end

  local key = sessionKey(parsed.game, parsed.arena)
  local session = sessions[key]
  if not session then
    -- Intents have no useful destination until an authority has announced
    -- the arena. Discovery messages and owner traffic may bootstrap it.
    if parsed.kind == "intent" then
      reject(parsed.senderPid, "no_session", "arena has no active authority", parsed.raw)
      return
    end
    -- A follower cannot allocate a session by forging authoritative traffic.
    -- Hello/resync/heartbeat remain valid follower-first discovery paths.
    if (parsed.kind == "state" or parsed.kind == "command")
        and parsed.senderPid ~= parsed.hostPid then
      reject(
        parsed.senderPid,
        "not_authority",
        "only the prop owner may publish state or commands",
        parsed.raw)
      return
    end
    session = newSession(parsed)
  end

  if not sequenceIsFresh(session, parsed) then return end

  if parsed.kind == "state" or parsed.kind == "command" then
    if parsed.senderPid ~= session.hostPid then
      reject(
        parsed.senderPid,
        "not_authority",
        "only the prop owner may publish state or commands",
        parsed.raw,
        session)
      return
    end
    if not epochMatches(session, parsed) then return end
  elseif parsed.kind == "intent" then
    if not session.ready then
      reject(parsed.senderPid, "not_ready", "arena authority is not ready", parsed.raw, session)
      return
    end
    if not epochMatches(session, parsed) then return end
  end

  acceptSequence(session, parsed)
  if parsed.senderPid == session.hostPid then session.ready = true end

  if parsed.kind == "hello" then
    sendRole(session, parsed.senderPid)
    sendCachedState(session, parsed.senderPid)
  elseif parsed.kind == "resync" then
    sendRole(session, parsed.senderPid)
    sendCachedState(session, parsed.senderPid)
  elseif parsed.kind == "heartbeat" then
    -- Heartbeats double as a cheap recovery path if a role response was lost.
    sendRole(session, parsed.senderPid)
  elseif parsed.kind == "state" then
    session.revision = session.revision + 1
    session.latestState = parsed.body
    session.latestStateRevision = session.revision
    broadcast(
      session,
      "state",
      session.latestState,
      parsed.senderPid,
      session.latestStateRevision)
  elseif parsed.kind == "command" then
    session.revision = session.revision + 1
    broadcast(session, "command", parsed.body, parsed.senderPid)
  elseif parsed.kind == "intent" then
    -- Only the host receives requests.  Followers must never observe an
    -- intent as if it were an authoritative gameplay command.
    safeSend(
      session.hostPid,
      envelopeFor(session, "intent", parsed.body, parsed.senderPid))
  end
end

local function closeSession(key, session, reason, extra)
  local body = {reason = reason}
  if type(extra) == "table" then
    for name, value in pairs(extra) do body[name] = value end
  end
  broadcast(session, "closed", body)
  sessions[key] = nil
end

local function keysForArena(arena)
  local keys = {}
  for key, session in pairs(sessions) do
    if session.arena == arena then keys[#keys + 1] = key end
  end
  return keys
end

function ericrolphGamesOnPlayerDisconnect(playerID)
  local disconnected = normalizePid(playerID)
  if disconnected == nil then return end
  local closing = {}
  for key, session in pairs(sessions) do
    if session.hostPid == disconnected then
      closing[#closing + 1] = key
    else
      session.lastSeq[disconnected] = nil
    end
  end
  for _, key in ipairs(closing) do
    local session = sessions[key]
    if session then
      closeSession(key, session, "host_disconnected", {hostPid = disconnected})
    end
  end
end

function ericrolphGamesOnVehicleDeleted(playerID, vehicleID)
  local pid = normalizePid(playerID)
  local vid = normalizePid(vehicleID)
  if pid == nil or vid == nil then return end
  local arena = tostring(pid) .. "-" .. tostring(vid)
  for _, key in ipairs(keysForArena(arena)) do
    local session = sessions[key]
    if session then
      closeSession(key, session, "arena_deleted", {hostPid = pid, vehicleId = vid})
    end
  end
end

function ericrolphGamesOnVehicleReset(playerID, vehicleID)
  local pid = normalizePid(playerID)
  local vid = normalizePid(vehicleID)
  if pid == nil or vid == nil then return end
  local arena = tostring(pid) .. "-" .. tostring(vid)
  for _, key in ipairs(keysForArena(arena)) do
    local session = sessions[key]
    if session then
      if session.epoch >= MAX_SAFE_EPOCH then
        closeSession(key, session, "epoch_exhausted", {hostPid = pid, vehicleId = vid})
      else
        local previousEpoch = session.epoch
        session.epoch = previousEpoch + 1
        session.lastSeq = {}
        session.revision = 0
        session.latestState = nil
        session.latestStateRevision = nil
        session.ready = false
        broadcast(session, "closed", {
          reason = "arena_reset",
          previousEpoch = previousEpoch,
          nextEpoch = session.epoch,
          hostPid = pid,
          vehicleId = vid,
        })
      end
    end
  end
end

function onInit()
  if registered then return end
  MP.RegisterEvent(C2S_EVENT, "ericrolphGamesOnClientEvent")
  MP.RegisterEvent("onPlayerDisconnect", "ericrolphGamesOnPlayerDisconnect")
  MP.RegisterEvent("onVehicleDeleted", "ericrolphGamesOnVehicleDeleted")
  MP.RegisterEvent("onVehicleReset", "ericrolphGamesOnVehicleReset")
  registered = true
end
