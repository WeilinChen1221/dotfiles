local mp = require('mp')
local utils = require('mp.utils')

local function test()
    package.path = assert(os.getenv('MPVACIOUS_ROOT')) .. '/?.lua;' .. package.path
    local h = require('helpers')
    local clock = 0
    local timers = {}
    local files = { ['/mock/pyproject.toml'] = 'project', ['/mock/uv.lock'] = 'lock' }
    local original_open = io.open
    io.open = function(path, mode)
        if mode == 'rb' then
            if files[path] == nil then return nil end
            return { read = function() return files[path] end, close = function() end }
        end
        return {
            write = function(_, data) files[path] = data end,
            close = function() end,
        }
    end
    mp.get_time = function() return clock end
    mp.add_timeout = function(_, fn) table.insert(timers, fn) end
    utils.file_info = function() return { is_file = true } end
    h.find_mpvacious_dir = function() return '/mock' end
    h.notify = function() end
    local setup
    local launches = 0
    local launched
    local launch_status = 0
    h.subprocess = function(o) setup = o end
    h.subprocess_detached = function(o)
        launches = launches + 1
        launched = o.args
        return { status = launch_status }
    end
    package.loaded['encoder.executables'] = { find_exec = function() return '/mock/uv' end }
    package.loaded['history.server_process'] = nil
    local factory = require('history.server_process')
    local config = {
        mining_history_url = 'http://127.0.0.1:44765', mining_history_db = '/mock/db',
        mining_history_autostart = true,
    }
    local probes = {}
    local function instance()
        return factory.new({ query = function(key) return config[key] end }, {
            health = function(callback) table.insert(probes, callback) end,
        })
    end
    local function health(ok, incompatible)
        local callback = table.remove(probes, 1)
        assert(callback, 'missing health probe')
        callback(ok, ok and nil or 'not ready', incompatible)
    end
    local process = instance()
    local completed = 0
    process.ensure_running(function(ok) assert(ok); completed = completed + 1 end)
    process.ensure_running(function(ok) assert(ok); completed = completed + 1 end)
    assert(#probes == 1 and completed == 0)
    health(false)
    assert(setup.args[2] == 'sync' and h.contains(setup.args, '--locked'))
    assert(launches == 0)
    setup.completion_fn(true, { status = 0 })
    assert(files['/mock/.venv/mpvoracious-ready'] == 'projectlock')
    assert(launches == 1 and h.contains(launched, '--no-sync'))
    assert(not h.contains(launched, '--isolated'))
    health(false)
    assert(completed == 0)
    table.remove(timers, 1)()
    health(true)
    assert(completed == 2 and process.state == 'ready')

    -- A dead helper can be launched again, reusing its prepared environment.
    setup = nil
    process.ensure_running()
    health(false)
    assert(setup == nil and launches == 2)
    health(true)

    -- Failed launch retains its error, backs off, and then permits a retry.
    launch_status = 1
    process.ensure_running(function(ok, error) assert(not ok and error) end)
    health(false)
    assert(process.state == 'failed' and process.last_error)
    local count = launches
    process.ensure_running()
    assert(#probes == 0 and launches == count)
    clock = 40
    launch_status = 0
    process.ensure_running()
    health(false)
    health(true)
    assert(process.state == 'ready')

    -- Never start another server over an incompatible live server.
    local incompatible = instance()
    incompatible.ensure_running(function(ok) assert(not ok) end)
    count = launches
    health(false, true)
    assert(launches == count and incompatible.state == 'failed')

    -- Readiness timeout releases waiting callers with the retained server log.
    files['/mock/.venv/history-server.log'] = 'bind failed'
    local timeout = instance()
    timeout.ensure_running(function(ok, error) assert(not ok and error:find('bind failed', 1, true)) end)
    health(false)
    clock = clock + 20
    health(false)
    assert(timeout.state == 'failed')

    -- Metadata changes trigger setup; setup errors are visible and retryable.
    files['/mock/uv.lock'] = 'new lock'
    local changed = instance()
    changed.ensure_running(function(ok, error) assert(not ok and error:find('offline', 1, true)) end)
    health(false)
    assert(setup)
    setup.completion_fn(true, { status = 1, stderr = 'offline' })
    assert(changed.state == 'failed')
    io.open = original_open
end

local success, error = pcall(test)
if success then mp.msg.info('TESTS PASSED') else mp.msg.error('TESTS FAILED: ' .. tostring(error)) end
mp.commandv('quit', success and 0 or 1)
