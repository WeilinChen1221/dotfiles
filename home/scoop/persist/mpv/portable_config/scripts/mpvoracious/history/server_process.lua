local mp = require('mp')
local utils = require('mp.utils')
local h = require('helpers')
local executables = require('encoder.executables')

local function read_file(path)
    local file = io.open(path, 'rb')
    if not file then return nil end
    local content = file:read('*a')
    file:close()
    return content
end

local function new(cfg_mgr, client)
    local self = { state = 'idle', last_error = nil, retry_at = 0 }
    local waiting = {}
    local failures = 0
    local started_at
    local plugin_dir = h.find_mpvacious_dir()
    local marker = utils.join_path(plugin_dir, '.venv/mpvoracious-ready')
    local log_path = utils.join_path(plugin_dir, '.venv/history-server.log')

    local function fingerprint()
        return (read_file(utils.join_path(plugin_dir, 'pyproject.toml')) or '')
                .. (read_file(utils.join_path(plugin_dir, 'uv.lock')) or '')
    end

    local function finish(ok, error)
        self.state = ok and 'ready' or 'failed'
        self.last_error = error
        failures = ok and 0 or failures + 1
        self.retry_at = ok and 0 or mp.get_time() + math.min(30, 2 ^ failures)
        local callbacks = waiting
        waiting = {}
        if error then mp.msg.error(error) end
        for _, callback in ipairs(callbacks) do callback(ok, error) end
    end

    local function poll_ready()
        client.health(function(ok, error, incompatible)
            if ok then return finish(true) end
            if incompatible then return finish(false, error) end
            if mp.get_time() - started_at >= 15 then
                local detail = read_file(log_path) or error or ''
                return finish(false, 'History server did not start: ' .. detail:sub(-2000))
            end
            mp.add_timeout(0.25, poll_ready)
        end)
    end

    local function launch()
        local url = cfg_mgr.query('mining_history_url')
        local host, port = url:match('^http://([^:/]+):?(%d*)/?$')
        if not host then
            return finish(false, 'History autostart requires an http://host:port URL.')
        end
        local args = {
            executables.find_exec('uv'), 'run', '--no-sync', '--project', plugin_dir,
            'python', '-m', 'history_server', '--host', host,
            '--port', port ~= '' and port or '44765', '--log-file', log_path,
        }
        local db_path = cfg_mgr.query('mining_history_db')
        if not h.is_empty(db_path) then
            args = h.join_lists(args, { '--db', db_path })
        end
        local result = h.subprocess_detached { args = args, suppress_log = true }
        if type(result) ~= 'table' or result.status ~= 0 then
            return finish(false, 'Could not launch history server: ' .. tostring(result and result.error_string or 'uv unavailable'))
        end
        started_at = mp.get_time()
        poll_ready()
    end

    local function prepare()
        local interpreter = utils.join_path(plugin_dir, h.is_win() and '.venv/Scripts/python.exe' or '.venv/bin/python')
        if read_file(marker) == fingerprint() and utils.file_info(interpreter) then
            return launch()
        end
        h.notify('Preparing Mining History Python environment. See the mpv log if setup fails.', 'info', 5)
        h.subprocess {
            args = { executables.find_exec('uv'), 'sync', '--locked', '--no-dev', '--project', plugin_dir },
            suppress_log = true,
            completion_fn = function(success, result, error)
                if not success or not result or result.status ~= 0 then
                    return finish(false, 'History environment setup failed: ' .. tostring(result and result.stderr or error))
                end
                local file, file_error = io.open(marker, 'wb')
                if not file then return finish(false, 'Cannot save history environment marker: ' .. tostring(file_error)) end
                file:write(fingerprint())
                file:close()
                launch()
            end,
        }
    end

    function self.ensure_running(callback)
        if self.state == 'failed' and mp.get_time() < self.retry_at then
            if callback then callback(false, self.last_error) end
            return
        end
        if callback then table.insert(waiting, callback) end
        if self.state == 'starting' then return end
        self.state = 'starting'
        client.health(function(ok, error, incompatible)
            if ok then return finish(true) end
            if incompatible then return finish(false, error) end
            if cfg_mgr.query('mining_history_autostart') ~= true then
                return finish(false, error or 'History server is unavailable and autostart is disabled.')
            end
            prepare()
        end)
    end

    function self.open_page()
        local platform = require('platform.init')
        return h.subprocess_detached {
            args = { platform.open_utility, cfg_mgr.query('mining_history_url') },
            suppress_log = true,
        }
    end

    return self
end

return { new = new }
