-- BeamNG MCP localhost WebSocket client.
-- Install under <BeamNG user path>/mods/unpacked/beamng_mcp/lua/ge/extensions/.
-- BeamNG's Lua runtime varies by release. This adapter uses the built-in
-- websocket module when present and fails closed when unavailable.

local M = {}
local json = require('json')
local ws = nil
local connected = false
local reconnectAt = 0

local URL = os.getenv('BEAMNG_MCP_LUA_WS_URL') or 'ws://127.0.0.1:8765'
local SECRET = os.getenv('BEAMNG_MCP_LUA_SHARED_SECRET') or 'change-me'

local handlers = {}

handlers.ping = function(args)
  return {pong = true, time = os.time()}
end

handlers.getVehicleData = function(args)
  local objectId = tonumber(args.objectId)
  local vehicle = objectId and be:getObjectByID(objectId) or be:getPlayerVehicle(0)
  if not vehicle then return nil, 'vehicle not found' end
  return {
    objectId = vehicle:getID(),
    position = {vehicle:getPosition():toTable()},
    velocity = {vehicle:getVelocity():toTable()}
  }
end

handlers.setTimeOfDay = function(args)
  if not core_environment then return nil, 'core_environment unavailable' end
  core_environment.setTimeOfDay({time = tonumber(args.time) or 0.5, play = false})
  return {ok = true}
end

handlers.spawnPrefab = function(args)
  if type(args.path) ~= 'string' or args.path:find('%.%.', 1, true) then
    return nil, 'invalid prefab path'
  end
  local name = tostring(args.name or 'mcp_prefab'):gsub('[^%w_%-]', '_')
  local id = spawnPrefab(name, args.path, args.position or '0 0 0', args.rotation or '0 0 1 0', args.scale or '1 1 1')
  return {objectId = id}
end

handlers.removeObject = function(args)
  local id = tonumber(args.objectId)
  local object = id and scenetree.findObjectById(id)
  if not object then return nil, 'object not found' end
  object:delete()
  return {removed = id}
end

local function send(value)
  if ws and connected then ws:send(jsonEncode(value)) end
end

local function onMessage(message)
  local ok, request = pcall(jsonDecode, message)
  if not ok or type(request) ~= 'table' then return end
  local handler = handlers[request.op]
  if not handler then
    send({id = request.id, ok = false, error = 'operation not allowed'})
    return
  end
  local callOk, result, err = pcall(handler, request.args or {})
  send({id = request.id, ok = callOk and result ~= nil, result = result, error = callOk and err or result})
end

local function connect()
  local ok, websocket = pcall(require, 'websocket')
  if not ok then
    log('E', 'beamngMcp', 'No websocket module in this BeamNG build; use BeamNGpy-only tools or install a compatible websocket module.')
    reconnectAt = os.clock() + 10
    return
  end
  ws = websocket.new(URL)
  ws:on('open', function()
    connected = true
    ws:send(jsonEncode({secret = SECRET, client = 'beamng-lua'}))
    log('I', 'beamngMcp', 'Connected to local MCP bridge')
  end)
  ws:on('message', onMessage)
  ws:on('close', function() connected = false; reconnectAt = os.clock() + 2 end)
  ws:connect()
end

function M.onExtensionLoaded()
  connect()
end

function M.onUpdate(dtReal, dtSim, dtRaw)
  if ws and ws.update then ws:update() end
  if not connected and os.clock() >= reconnectAt then connect() end
end

function M.onExtensionUnloaded()
  if ws then ws:close() end
  connected = false
end

return M

