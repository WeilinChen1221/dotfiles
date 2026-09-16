--[[
Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

The new note timer feature allows mpvacious to automatically detect and update new Anki notes.
When enabled, mpvacious will periodically check for new notes
and automatically add media (audio and images) to them if they match your configured note type.
]]

local mp = require('mp')
local msg = require('mp.msg')
local h = require('helpers')
local normalizer = require('history.normalizer')

local function classify_claim(claim, error)
    if not h.is_empty(error) or type(claim) ~= "table" then
        return "retry"
    elseif claim.status == "claimed" and not h.is_empty(claim.record) then
        return "claimed"
    elseif claim.status == "already_claimed" then
        return "handled"
    elseif claim.status == "unmatched" then
        return "fallback"
    end
    return "retry"
end

local function sentences_match(first, second, config)
    if h.is_empty(first) or h.is_empty(second) then
        return false
    end
    return normalizer.normalize(first, config) == normalizer.normalize(second, config)
end

local function make_anki_new_note_checker()
    local self = { busy = false }
    local ignored = {}
    local ignored_scope
    local started_at

    local function history_enabled()
        return self.history_controller and self.history_controller.enabled()
    end

    local function scope()
        -- A cursor belongs to the Anki destination and matching configuration.
        return require('mp.utils').format_json({
            self.config.ankiconnect_url, self.config.deck_name, self.config.model_name,
            self.config.sentence_field, self.config.audio_field, self.config.image_field,
            self.cfg_mgr.profiles().active, self.config.nuke_spaces,
        })
    end

    local function has_no_media(fields)
        return h.is_empty(fields[self.config.audio_field]) and h.is_empty(fields[self.config.image_field])
    end

    local function matches_current(fields)
        if type(self.current_sentence_fn) ~= 'function' then return false end
        local ok, sentence = pcall(self.current_sentence_fn)
        return ok and sentences_match(fields[self.config.sentence_field], sentence, self.config)
    end

    local function finish(error)
        self.busy = false
        if error then msg.warn('Note discovery failed: ' .. tostring(error)) end
    end

    local function scan(cursor, scan_scope, scan_started)
        local use_history = history_enabled()
        local scan_error
        local overlap = (use_history and self.config.mining_history_match_window_minutes or 2) * 60000
        local since = math.max(0, (cursor or scan_started) - overlap)
        local days = math.max(1, math.ceil((scan_started - since) / 86400000) + 1)
        -- Keep only the recent in-memory cache. SQLite claims are authoritative across restarts.
        for note_id in pairs(ignored) do
            if note_id < since then ignored[note_id] = nil end
        end
        self.ankiconnect.find_notes {
            query = string.format('added:%d "note:%s" "deck:%s"', days, self.config.model_name, self.config.deck_name),
            suppress_log = true,
            completion_fn = function(note_ids, error)
                if error then return finish(error) end
                local candidates = {}
                for _, note_id in ipairs(note_ids or {}) do
                    if note_id >= since and not ignored[note_id] then
                        table.insert(candidates, note_id)
                    end
                end
                local function save_progress()
                    if scan_error then return finish(scan_error) end
                    if not use_history then return finish() end
                    self.history_controller.discovery(scan_scope, scan_started, function(_, save_error)
                        finish(save_error)
                    end)
                end
                local offset = 1
                local function next_batch()
                    if offset > #candidates then return save_progress() end
                    local batch = {}
                    for index = offset, math.min(offset + 99, #candidates) do
                        table.insert(batch, candidates[index])
                    end
                    offset = offset + #batch
                    self.ankiconnect.get_notes_fields_async(batch, function(notes, fields_error)
                        if fields_error then return finish(fields_error) end
                        local index = 0
                        local function next_note()
                            if use_history and scope() ~= scan_scope then
                                return finish('matching configuration changed during the scan')
                            end
                            index = index + 1
                            if index > #batch then return next_batch() end
                            local note_id = batch[index]
                            local fields = notes[note_id]
                            if not fields or h.is_empty(fields[self.config.sentence_field]) or not has_no_media(fields) then
                                ignored[note_id] = true
                                return next_note()
                            end
                            local function legacy_fallback()
                                -- Historical notes must never use media from the currently playing sentence.
                                if note_id >= started_at and note_id >= scan_started - 120000 and matches_current(fields) then
                                    self.update_notes_fn({ note_id }, false)
                                    ignored[note_id] = true
                                end
                                next_note()
                            end
                            if not use_history then return legacy_fallback() end
                            self.history_controller.claim_note(
                                note_id, normalizer.normalize(fields[self.config.sentence_field], self.config),
                                function(claim, claim_error)
                                    local action = classify_claim(claim, claim_error)
                                    if action == 'retry' then
                                        scan_error = claim_error or 'history match is ambiguous; scan will be retried'
                                        return next_note()
                                    elseif action == 'fallback' then
                                        return legacy_fallback()
                                    end
                                    -- Claiming has atomically queued delivery. The worker handles media.
                                    ignored[note_id] = true
                                    next_note()
                                end
                            )
                        end
                        next_note()
                    end)
                end
                next_batch()
            end,
        }
    end

    local function check_for_new_notes()
        if self.busy then return end
        self.busy = true
        local scan_started = os.time() * 1000
        if not history_enabled() then return scan(nil, nil, scan_started) end
        local scan_scope = scope()
        if ignored_scope ~= scan_scope then
            ignored = {}
            ignored_scope = scan_scope
        end
        self.history_controller.discovery(scan_scope, nil, function(parsed, error)
            if error or not parsed then return finish(error or 'history server unavailable') end
            local cursor = type(parsed.scanned_through) == 'number' and parsed.scanned_through or nil
            scan(cursor, scan_scope, scan_started)
        end)
    end

    local function start_timer()
        if not self.config or not self.config.enable_new_note_timer or self.timer then return end
        started_at = os.time() * 1000
        self.timer = mp.add_periodic_timer(self.config.new_note_timer_interval_seconds, check_for_new_notes)
        check_for_new_notes()
    end

    local function stop_timer()
        if self.timer then self.timer:kill(); self.timer = nil end
    end

    local function init(ankiconnect, update_notes_fn, history_controller, cfg_mgr, current_sentence_fn)
        cfg_mgr.fail_if_not_ready()
        self.ankiconnect = ankiconnect
        self.update_notes_fn = update_notes_fn
        self.history_controller = history_controller
        self.cfg_mgr = cfg_mgr
        self.config = cfg_mgr.config()
        self.current_sentence_fn = current_sentence_fn
    end

    return { start_timer = start_timer, stop_timer = stop_timer, init = init }
end

return {
    new = make_anki_new_note_checker,
    classify_claim = classify_claim,
    sentences_match = sentences_match,
}
