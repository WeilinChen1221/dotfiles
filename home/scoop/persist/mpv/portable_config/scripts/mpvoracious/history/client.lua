local utils = require('mp.utils')
local platform = require('platform.init')
local h = require('helpers')

local function new(cfg_mgr)
    local self = {}

    local function base_url()
        return cfg_mgr.query("mining_history_url"):gsub("/$", "")
    end

    local function parse_result(result)
        if type(result) ~= 'table' or result.status ~= 0 then
            return nil, 'history server unavailable: ' .. tostring(result and result.stderr or 'request failed')
        end
        local body, status = (result.stdout or ''):match('^(.*)\n(%d%d%d)$')
        if not status then
            return nil, 'history server returned no HTTP status'
        end
        local parsed = utils.parse_json(body)
        status = tonumber(status)
        if status < 200 or status >= 300 then
            return nil, string.format('HTTP %d: %s', status, type(parsed) == 'table' and parsed.error or body)
        end
        if type(parsed) ~= 'table' then
            return nil, 'history server returned invalid JSON'
        end
        if not h.is_empty(parsed.error) then
            return nil, tostring(parsed.error)
        end
        return parsed, nil
    end

    local function url_encode(str)
        return tostring(str):gsub('([^%w%-_%.~])', function(char)
            return string.format('%%%02X', string.byte(char))
        end)
    end

    local function completion(callback)
        callback = callback or h.noop
        return function(success, result, error)
            if not success or not h.is_empty(error) then
                return callback(nil, tostring(error or 'request failed'))
            end
            callback(parse_result(result))
        end
    end

    local function post(path, payload, callback)
        local request_json, error = utils.format_json(payload)
        if error ~= nil or request_json == 'null' then
            return (callback or h.noop)(nil, 'failed to format JSON')
        end
        return platform.json_curl_request {
            url = base_url() .. path,
            request_json = request_json,
            http_status = true,
            suppress_log = true,
            completion_fn = completion(callback),
        }
    end

    local function get(path, callback)
        return platform.curl_request {
            args = { '-sS', '--connect-timeout', '2', '--max-time', '5',
                     '--write-out', '\n%{http_code}', base_url() .. path },
            suppress_log = true,
            completion_fn = completion(callback),
        }
    end

    function self.health(callback)
        return get('/health', function(parsed, error)
            if not parsed then return callback(false, error, false) end
            local compatible = parsed.service == 'mpvoracious-history' and parsed.protocol_version == 2
            if not compatible then
                return callback(false, 'An incompatible history server is already running. Stop the old helper and restart mpv.', true)
            end
            callback(parsed.ok == true, parsed.ok ~= true and 'history server is not ready' or nil, false)
        end)
    end

    function self.discovery(scope, scanned_through, callback)
        return post('/api/discovery', { scope = scope, scanned_through = scanned_through }, callback)
    end

    function self.create_record(record, completion_fn)
        return post('/api/records', record, completion_fn)
    end

    function self.claim_note(note_id, normalized_sentence, completion_fn)
        return post('/api/claims', {
            note_id = note_id,
            note_created_at = note_id / 1000,
            normalized_sentence = normalized_sentence,
            window_minutes = cfg_mgr.query("mining_history_match_window_minutes"),
            profile = cfg_mgr.profiles().active,
            audio_field = cfg_mgr.query("audio_field"),
            image_field = cfg_mgr.query("image_field"),
        }, completion_fn)
    end

    function self.find_pending(normalized_sentence, completion_fn)
        local escaped = url_encode(normalized_sentence)
        return get('/api/pending?normalized_sentence=' .. escaped .. '&window_minutes=' .. tostring(cfg_mgr.query("mining_history_match_window_minutes")), completion_fn)
    end

    function self.list_records(completion_fn)
        return get('/api/records', completion_fn)
    end

    function self.consume_preview(completion_fn)
        return get('/api/preview', completion_fn)
    end

    function self.update_status(record_id, status, note_id, error, completion_fn)
        return post('/api/records/' .. url_encode(record_id) .. '/status', {
            status = status,
            note_id = note_id,
            error = error or '',
        }, completion_fn)
    end

    function self.remove_missing_note(record_id, note_id, completion_fn)
        return post('/api/records/' .. url_encode(record_id) .. '/missing-note', {
            note_id = note_id,
        }, completion_fn)
    end

    function self.lease_resend(completion_fn)
        return post('/api/resends/lease', { lease_seconds = 30 }, completion_fn)
    end

    function self.renew_resend(generation_id, lease_token, completion_fn)
        return post('/api/resends/' .. tostring(generation_id) .. '/renew', {
            lease_token = lease_token,
            lease_seconds = 30,
        }, completion_fn)
    end

    function self.adopt_targets(generation_id, lease_token, note_id, audio_field, image_field, completion_fn)
        return post('/api/resends/' .. tostring(generation_id) .. '/targets', {
            lease_token = lease_token,
            note_id = note_id,
            audio_field = audio_field,
            image_field = image_field,
        }, completion_fn)
    end

    function self.report_resend(generation_id, lease_token, note_id, state, error, completion_fn)
        return post('/api/resends/' .. tostring(generation_id) .. '/result', {
            lease_token = lease_token,
            note_id = note_id,
            state = state,
            error = error or '',
        }, completion_fn)
    end

    function self.finalize_resend(generation_id, lease_token, error, completion_fn)
        return post('/api/resends/' .. tostring(generation_id) .. '/complete', {
            lease_token = lease_token,
            error = error or '',
        }, completion_fn)
    end

    return self
end

return {
    new = new,
}
