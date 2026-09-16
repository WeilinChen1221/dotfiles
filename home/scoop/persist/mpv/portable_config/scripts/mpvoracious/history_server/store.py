from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable


VALID_STATUSES = {"pending_note", "matched_note", "media_done", "media_failed"}


class InvalidStatusError(ValueError):
    pass


class NoLinkedNotesError(ValueError):
    pass


class StaleLeaseError(ValueError):
    pass


def default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "mpvacious" / "mining_history.sqlite3"


def _human_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int(seconds // 60) % 60
    whole_seconds = int(seconds) % 60
    milliseconds = int(seconds * 1000) % 1000
    result = f"{minutes:02d}m{whole_seconds:02d}s{milliseconds:03d}ms"
    return f"{hours}h{result}" if hours else result


def _legacy_source_info(filename: str, snapshot_time: float) -> str:
    display_name = filename or "Unknown source"
    return f"{display_name} ({_human_time(snapshot_time)})"


def _like_value(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class HistoryStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

    @staticmethod
    def _add_columns(
        conn: sqlite3.Connection,
        table: str,
        definitions: dict[str, str],
    ) -> set[str]:
        existing = HistoryStore._columns(conn, table)
        added: set[str] = set()
        for name, definition in definitions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                added.add(name)
        return added

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    sequence INTEGER NOT NULL,
                    id TEXT PRIMARY KEY,
                    sentence TEXT NOT NULL,
                    normalized_sentence TEXT NOT NULL,
                    secondary TEXT NOT NULL DEFAULT '',
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    snapshot_time REAL NOT NULL,
                    video_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note_id INTEGER,
                    error TEXT NOT NULL DEFAULT '',
                    source_info TEXT NOT NULL DEFAULT '',
                    video_track_id TEXT,
                    video_ff_index TEXT,
                    audio_track_id TEXT,
                    audio_ff_index TEXT,
                    audio_external_path TEXT NOT NULL DEFAULT '',
                    has_audio INTEGER,
                    has_video INTEGER,
                    source_duration REAL,
                    capture_volume REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            record_columns = self._columns(conn, "records")
            if "sequence" not in record_columns:
                conn.execute("ALTER TABLE records ADD COLUMN sequence INTEGER")
                conn.execute("UPDATE records SET sequence = rowid WHERE sequence IS NULL")
            self._add_columns(
                conn,
                "records",
                {
                    "source_info": "TEXT NOT NULL DEFAULT ''",
                    "video_track_id": "TEXT",
                    "video_ff_index": "TEXT",
                    "audio_track_id": "TEXT",
                    "audio_ff_index": "TEXT",
                    "audio_external_path": "TEXT NOT NULL DEFAULT ''",
                    "has_audio": "INTEGER",
                    "has_video": "INTEGER",
                    "source_duration": "REAL",
                    "capture_volume": "REAL",
                },
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_sequence ON records (sequence)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS note_claims (
                    note_id INTEGER PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    audio_field TEXT NOT NULL DEFAULT '',
                    image_field TEXT NOT NULL DEFAULT '',
                    delivery_state TEXT NOT NULL DEFAULT 'pending',
                    delivery_error TEXT NOT NULL DEFAULT '',
                    delivery_updated_at REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )
            added_claim_columns = self._add_columns(
                conn,
                "note_claims",
                {
                    "audio_field": "TEXT NOT NULL DEFAULT ''",
                    "image_field": "TEXT NOT NULL DEFAULT ''",
                    "delivery_state": "TEXT NOT NULL DEFAULT 'pending'",
                    "delivery_error": "TEXT NOT NULL DEFAULT ''",
                    "delivery_updated_at": "REAL NOT NULL DEFAULT 0",
                },
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_claims_record ON note_claims (record_id)"
            )
            conn.execute("DROP INDEX IF EXISTS idx_records_match")
            conn.execute(
                """
                CREATE INDEX idx_records_match
                ON records (normalized_sentence, profile, created_at DESC, sequence DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preview_requests (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    record_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resend_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    lease_token TEXT,
                    lease_expires_at REAL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_resend_active_record
                ON resend_generations (record_id)
                WHERE state IN ('pending', 'leased')
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_resend_pending
                ON resend_generations (state, created_at, id)
                """
            )
            conn.execute("DROP INDEX IF EXISTS idx_records_pending_match")
            conn.execute(
                """
                CREATE INDEX idx_records_pending_match
                ON records (normalized_sentence, created_at DESC, sequence DESC)
                WHERE status = 'pending_note'
                """
            )

            for row in conn.execute(
                "SELECT id, filename, snapshot_time FROM records WHERE source_info = ''"
            ):
                conn.execute(
                    "UPDATE records SET source_info = ? WHERE id = ?",
                    (_legacy_source_info(row["filename"], row["snapshot_time"]), row["id"]),
                )

            # Databases from before relationship-owned delivery may only have records.note_id.
            conn.execute(
                """
                INSERT OR IGNORE INTO note_claims (
                    note_id, record_id, delivery_state, delivery_error,
                    delivery_updated_at, created_at
                )
                SELECT note_id, id,
                    CASE status
                        WHEN 'media_done' THEN 'done'
                        WHEN 'media_failed' THEN 'failed'
                        WHEN 'matched_note' THEN 'in_progress'
                        ELSE 'pending'
                    END,
                    error, updated_at, created_at
                FROM records
                WHERE note_id IS NOT NULL
                """
            )
            if "delivery_state" in added_claim_columns:
                conn.execute(
                    """
                    UPDATE note_claims
                    SET delivery_state = CASE COALESCE(
                            (SELECT status FROM records WHERE id = note_claims.record_id),
                            'pending_note'
                        )
                        WHEN 'media_done' THEN 'done'
                        WHEN 'media_failed' THEN 'failed'
                        WHEN 'matched_note' THEN 'in_progress'
                        ELSE 'pending'
                    END,
                    delivery_error = COALESCE(
                        (SELECT error FROM records WHERE id = note_claims.record_id), ''
                    ),
                    delivery_updated_at = COALESCE(
                        (SELECT updated_at FROM records WHERE id = note_claims.record_id),
                        created_at
                    )
                    """
                )
            migrating_jobs = not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'delivery_members'"
            ).fetchone()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_members (
                    generation_id INTEGER NOT NULL REFERENCES resend_generations(id) ON DELETE CASCADE,
                    note_id INTEGER NOT NULL REFERENCES note_claims(note_id) ON DELETE CASCADE,
                    initial_delivery INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (generation_id, note_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovery_cursors (
                    scope TEXT PRIMARY KEY,
                    scanned_through INTEGER NOT NULL
                )
                """
            )
            if migrating_jobs:
                # Existing generations are media-only resends. Keep their semantics.
                conn.execute(
                    """
                    INSERT INTO delivery_members (generation_id, note_id)
                    SELECT g.id, n.note_id FROM resend_generations g
                    JOIN note_claims n ON n.record_id = g.record_id
                    WHERE g.state IN ('pending', 'leased')
                    """
                )
            for row in conn.execute("SELECT id FROM records"):
                self._queue_initial_deliveries(conn, row["id"])
                self._recalculate_record(conn, row["id"])

    @staticmethod
    def _queue_initial_deliveries(conn: sqlite3.Connection, record_id: str) -> None:
        """Attach unassigned claims to pending work, never mutate a leased batch."""
        generation = conn.execute(
            "SELECT * FROM resend_generations WHERE record_id = ? AND state IN ('pending', 'leased')",
            (record_id,),
        ).fetchone()
        if generation is not None and generation["state"] == "leased":
            return
        notes = conn.execute(
            """
            SELECT note_id FROM note_claims n
            WHERE record_id = ? AND delivery_state IN ('pending', 'in_progress')
                AND NOT EXISTS (
                    SELECT 1 FROM delivery_members m JOIN resend_generations g ON g.id = m.generation_id
                    WHERE m.note_id = n.note_id AND g.state IN ('pending', 'leased')
                )
            """,
            (record_id,),
        ).fetchall()
        if not notes:
            return
        if generation is None:
            now = time.time()
            cursor = conn.execute(
                "INSERT INTO resend_generations (record_id, state, created_at, updated_at) VALUES (?, 'pending', ?, ?)",
                (record_id, now, now),
            )
            generation_id = cursor.lastrowid
        else:
            generation_id = generation["id"]
        conn.executemany(
            "INSERT INTO delivery_members (generation_id, note_id, initial_delivery) VALUES (?, ?, 1)",
            [(generation_id, note["note_id"]) for note in notes],
        )

    @staticmethod
    def _settle_pending_generations(conn: sqlite3.Connection, record_id: str) -> None:
        # Compatibility for status updates and notes deleted before a worker leases them.
        conn.execute(
            """
            UPDATE resend_generations SET state = 'completed', updated_at = ?
            WHERE record_id = ? AND state = 'pending' AND NOT EXISTS (
                SELECT 1 FROM delivery_members m JOIN note_claims n ON n.note_id = m.note_id
                WHERE m.generation_id = resend_generations.id
                    AND n.delivery_state IN ('pending', 'in_progress')
            )
            """,
            (time.time(), record_id),
        )

    def discovery_cursor(self, scope: str, scanned_through: int | None = None) -> int | None:
        if not scope or len(scope) > 4096:
            raise ValueError("discovery scope is required and must not exceed 4096 characters")
        if scanned_through is not None and not 0 <= scanned_through <= int(time.time() * 1000):
            raise ValueError("invalid discovery timestamp")
        with self._connect() as conn:
            if scanned_through is not None:
                conn.execute(
                    """
                    INSERT INTO discovery_cursors VALUES (?, ?)
                    ON CONFLICT(scope) DO UPDATE SET scanned_through = MAX(scanned_through, excluded.scanned_through)
                    """,
                    (scope, scanned_through),
                )
            row = conn.execute("SELECT scanned_through FROM discovery_cursors WHERE scope = ?", (scope,)).fetchone()
            return row[0] if row else None

    @staticmethod
    def _link_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "note_id": row["note_id"],
            "audio_field": row["audio_field"],
            "image_field": row["image_field"],
            "delivery_state": row["delivery_state"],
            "delivery_error": row["delivery_error"],
            "delivery_updated_at": row["delivery_updated_at"],
            "created_at": row["created_at"],
        }

    def _record_from_row(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        record = dict(row)
        if record.get("has_audio") is not None:
            record["has_audio"] = bool(record["has_audio"])
        if record.get("has_video") is not None:
            record["has_video"] = bool(record["has_video"])
        links = conn.execute(
            """
            SELECT * FROM note_claims
            WHERE record_id = ?
            ORDER BY created_at, note_id
            """,
            (row["id"],),
        ).fetchall()
        linked_notes = [self._link_from_row(link) for link in links]
        record["linked_notes"] = linked_notes
        record["linked_note_ids"] = [link["note_id"] for link in linked_notes]
        record["linked_note_count"] = len(linked_notes)
        record["media_work_active"] = conn.execute(
            """
            SELECT 1 FROM resend_generations
            WHERE record_id = ? AND state IN ('pending', 'leased')
            """,
            (row["id"],),
        ).fetchone() is not None
        return record

    @staticmethod
    def _recalculate_record(conn: sqlite3.Connection, record_id: str) -> None:
        record_exists = conn.execute(
            "SELECT 1 FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if record_exists is None:
            return
        active = conn.execute(
            """
            SELECT 1 FROM resend_generations
            WHERE record_id = ? AND state IN ('pending', 'leased')
            """,
            (record_id,),
        ).fetchone()
        links = conn.execute(
            "SELECT note_id, delivery_state, delivery_error FROM note_claims WHERE record_id = ?",
            (record_id,),
        ).fetchall()
        if not links:
            status = "pending_note"
            error = ""
        elif active is not None or any(
            link["delivery_state"] in {"pending", "in_progress"} for link in links
        ):
            status = "matched_note"
            error = ""
        else:
            failures = [link for link in links if link["delivery_state"] == "failed"]
            if failures:
                status = "media_failed"
                parts = []
                for link in failures:
                    detail = link["delivery_error"] or "media delivery failed"
                    parts.append(f"Note {link['note_id']}: {detail}")
                error = "; ".join(parts)
            else:
                status = "media_done"
                error = ""
        conn.execute(
            "UPDATE records SET status = ?, error = ?, note_id = ?, updated_at = ? WHERE id = ?",
            (status, error, links[0]["note_id"] if links else None, time.time(), record_id),
        )

    @staticmethod
    def _expire_leases(conn: sqlite3.Connection, now: float) -> None:
        expired = conn.execute(
            """
            SELECT id, record_id FROM resend_generations
            WHERE state = 'leased' AND lease_expires_at <= ?
            """,
            (now,),
        ).fetchall()
        for generation in expired:
            conn.execute(
                """
                UPDATE resend_generations
                SET state = 'pending', lease_token = NULL, lease_expires_at = NULL,
                    error = 'worker lease expired', updated_at = ?
                WHERE id = ?
                """,
                (now, generation["id"]),
            )
            conn.execute(
                """
                UPDATE note_claims
                SET delivery_state = 'pending', delivery_error = '', delivery_updated_at = ?
                WHERE note_id IN (SELECT note_id FROM delivery_members WHERE generation_id = ?)
                    AND delivery_state = 'in_progress'
                """,
                (now, generation["id"]),
            )
            HistoryStore._recalculate_record(conn, generation["record_id"])

    @staticmethod
    def _require_active_lease(
        conn: sqlite3.Connection,
        generation_id: int,
        lease_token: str,
    ) -> sqlite3.Row:
        now = time.time()
        HistoryStore._expire_leases(conn, now)
        generation = conn.execute(
            "SELECT * FROM resend_generations WHERE id = ?",
            (generation_id,),
        ).fetchone()
        if (
            generation is None
            or generation["state"] != "leased"
            or not lease_token
            or not secrets.compare_digest(generation["lease_token"] or "", lease_token)
            or generation["lease_expires_at"] is None
            or generation["lease_expires_at"] <= now
        ):
            raise StaleLeaseError("stale or expired resend lease")
        return generation

    def add_record(self, record: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        filename = str(record["filename"])
        snapshot_time = float(record["snapshot_time"])
        source_info = str(record.get("source_info", "")).strip()
        values = {
            "id": str(record["id"]),
            "sentence": str(record["sentence"]),
            "normalized_sentence": str(record["normalized_sentence"]),
            "secondary": str(record.get("secondary", "")),
            "start_time": float(record["start_time"]),
            "end_time": float(record["end_time"]),
            "snapshot_time": snapshot_time,
            "video_path": str(record["video_path"]),
            "filename": filename,
            "profile": str(record["profile"]),
            "status": "pending_note",
            "note_id": None,
            "error": "",
            "source_info": source_info or _legacy_source_info(filename, snapshot_time),
            "video_track_id": record.get("video_track_id"),
            "video_ff_index": record.get("video_ff_index"),
            "audio_track_id": record.get("audio_track_id"),
            "audio_ff_index": record.get("audio_ff_index"),
            "audio_external_path": str(record.get("audio_external_path", "")),
            "has_audio": None if record.get("has_audio") is None else int(bool(record["has_audio"])),
            "has_video": None if record.get("has_video") is None else int(bool(record["has_video"])),
            "source_duration": record.get("source_duration"),
            "capture_volume": record.get("capture_volume"),
            "created_at": now,
            "updated_at": now,
        }
        if not values["id"] or not values["sentence"] or not values["profile"]:
            raise ValueError("record id, sentence, and profile are required")
        if values["end_time"] < values["start_time"]:
            raise ValueError("record end time must not precede start time")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            values["sequence"] = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM records"
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO records (
                    sequence, id, sentence, normalized_sentence, secondary,
                    start_time, end_time, snapshot_time, video_path, filename,
                    profile, status, note_id, error, source_info,
                    video_track_id, video_ff_index,
                    audio_track_id, audio_ff_index, audio_external_path,
                    has_audio, has_video, source_duration, capture_volume,
                    created_at, updated_at
                ) VALUES (
                    :sequence, :id, :sentence, :normalized_sentence, :secondary,
                    :start_time, :end_time, :snapshot_time, :video_path, :filename,
                    :profile, :status, :note_id, :error, :source_info,
                    :video_track_id, :video_ff_index,
                    :audio_track_id, :audio_ff_index, :audio_external_path,
                    :has_audio, :has_video, :source_duration, :capture_volume,
                    :created_at, :updated_at
                )
                """,
                values,
            )
        return self.get_record(values["id"])

    def get_record(self, record_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._expire_leases(conn, time.time())
            row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            return self._record_from_row(conn, row)

    def list_records(
        self,
        *,
        statuses: Iterable[str] = (),
        source_info: str = "",
        subtitle: str = "",
        profiles: Iterable[str] = (),
        note_id: int | None = None,
    ) -> dict[str, Any]:
        statuses = tuple(dict.fromkeys(statuses))
        profiles = tuple(dict.fromkeys(profiles))
        invalid_statuses = set(statuses) - VALID_STATUSES
        if invalid_statuses:
            raise InvalidStatusError(f"invalid status: {sorted(invalid_statuses)[0]}")
        if note_id is not None and note_id <= 0:
            raise ValueError("note_id must be a positive integer")

        conditions: list[str] = []
        params: list[Any] = []
        if statuses:
            conditions.append("r.status IN (" + ",".join("?" for _ in statuses) + ")")
            params.extend(statuses)
        if source_info:
            conditions.append("r.source_info LIKE ? ESCAPE '\\' COLLATE NOCASE")
            params.append(_like_value(source_info))
        if subtitle:
            conditions.append(
                "(r.sentence LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR r.secondary LIKE ? ESCAPE '\\' COLLATE NOCASE)"
            )
            value = _like_value(subtitle)
            params.extend((value, value))
        if profiles:
            conditions.append("r.profile IN (" + ",".join("?" for _ in profiles) + ")")
            params.extend(profiles)
        if note_id is not None:
            conditions.append(
                "EXISTS (SELECT 1 FROM note_claims nc "
                "WHERE nc.record_id = r.id AND nc.note_id = ?)"
            )
            params.append(note_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._expire_leases(conn, time.time())
            rows = conn.execute(
                f"""
                SELECT r.* FROM records r
                {where}
                ORDER BY r.created_at DESC, r.sequence DESC
                """,
                params,
            ).fetchall()
            records = [self._record_from_row(conn, row) for row in rows]
            available_profiles = [
                row["profile"]
                for row in conn.execute(
                    "SELECT DISTINCT profile FROM records ORDER BY profile COLLATE NOCASE"
                )
            ]
        return {
            "records": records,
            "profiles": available_profiles,
        }

    def find_pending_by_normalized_sentence(
        self, normalized_sentence: str, window_minutes: int
    ) -> dict[str, Any] | None:
        cutoff = time.time() - (window_minutes * 60)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM records
                WHERE normalized_sentence = ?
                    AND status = 'pending_note'
                    AND created_at >= ?
                ORDER BY created_at DESC, sequence DESC
                LIMIT 1
                """,
                (normalized_sentence, cutoff),
            ).fetchone()
            return self._record_from_row(conn, row) if row is not None else None

    def claim_note(
        self,
        note_id: int,
        normalized_sentence: str,
        window_minutes: int,
        profile: str = "",
        audio_field: str = "",
        image_field: str = "",
        note_created_at: float | None = None,
    ) -> dict[str, Any]:
        if note_id <= 0 or not normalized_sentence or window_minutes < 0:
            raise ValueError("invalid note claim")
        now = time.time()
        match_time = now if note_created_at is None else float(note_created_at)
        if not 0 <= match_time <= now + 5:
            raise ValueError("invalid note creation time")
        cutoff = match_time - (window_minutes * 60)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            claimed = conn.execute(
                "SELECT 1 FROM note_claims WHERE note_id = ?", (note_id,)
            ).fetchone()
            if claimed is not None:
                return {"status": "already_claimed", "record": None, "link": None}
            record = None
            if profile:
                # Prefer the Capture Profile used by this worker, but do not make
                # its local profile name a hard ownership boundary. Separate mpv
                # processes (or two equivalent profiles) can observe the same
                # Anki note, while the record itself owns the media settings.
                record = conn.execute(
                    """
                    SELECT * FROM records
                    WHERE normalized_sentence = ?
                        AND created_at >= ?
                        AND created_at <= ?
                        AND profile = ?
                    ORDER BY created_at DESC, sequence DESC
                    LIMIT 1
                    """,
                    (normalized_sentence, cutoff, match_time, profile),
                ).fetchone()
            if record is None:
                candidates = conn.execute(
                    """
                    SELECT * FROM records
                    WHERE normalized_sentence = ? AND created_at >= ? AND created_at <= ?
                    ORDER BY created_at DESC, sequence DESC
                    LIMIT 2
                    """,
                    (normalized_sentence, cutoff, match_time),
                ).fetchall()
                if profile and len(candidates) > 1:
                    return {"status": "ambiguous", "record": None, "link": None}
                if candidates:
                    record = candidates[0]
            if record is None:
                return {"status": "unmatched", "record": None, "link": None}
            conn.execute(
                """
                INSERT INTO note_claims (
                    note_id, record_id, audio_field, image_field,
                    delivery_state, delivery_error, delivery_updated_at, created_at
                ) VALUES (?, ?, ?, ?, 'pending', '', ?, ?)
                """,
                (note_id, record["id"], audio_field, image_field, now, now),
            )
            conn.execute(
                "UPDATE records SET note_id = ?, updated_at = ? WHERE id = ?",
                (note_id, now, record["id"]),
            )
            self._queue_initial_deliveries(conn, record["id"])
            self._recalculate_record(conn, record["id"])
            refreshed = conn.execute(
                "SELECT * FROM records WHERE id = ?", (record["id"],)
            ).fetchone()
            link = conn.execute(
                "SELECT * FROM note_claims WHERE note_id = ?", (note_id,)
            ).fetchone()
            return {
                "status": "claimed",
                "record": self._record_from_row(conn, refreshed),
                "link": self._link_from_row(link),
            }

    def update_status(
        self,
        record_id: str,
        status: str,
        note_id: int | None,
        error: str,
    ) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise InvalidStatusError(status)
        if status != "pending_note" and (not isinstance(note_id, int) or note_id <= 0):
            raise ValueError("note_id is required for media delivery status")
        state_by_status = {
            "matched_note": "in_progress",
            "media_done": "done",
            "media_failed": "failed",
        }
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            if record is None:
                raise KeyError(record_id)
            if status != "pending_note":
                link = conn.execute(
                    "SELECT 1 FROM note_claims WHERE note_id = ? AND record_id = ?",
                    (note_id, record_id),
                ).fetchone()
                if link is None:
                    # Transitional compatibility for old clients that updated status before claiming.
                    conn.execute(
                        """
                        INSERT INTO note_claims (
                            note_id, record_id, delivery_state, delivery_error,
                            delivery_updated_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (note_id, record_id, state_by_status[status], error, now, now),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE note_claims
                        SET delivery_state = ?, delivery_error = ?, delivery_updated_at = ?
                        WHERE note_id = ? AND record_id = ?
                        """,
                        (state_by_status[status], error, now, note_id, record_id),
                    )
                conn.execute(
                    "UPDATE records SET note_id = ?, updated_at = ? WHERE id = ?",
                    (note_id, now, record_id),
                )
            self._settle_pending_generations(conn, record_id)
            self._recalculate_record(conn, record_id)
            refreshed = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            return self._record_from_row(conn, refreshed)

    def remove_missing_note(self, record_id: str, note_id: int) -> dict[str, Any]:
        if note_id <= 0:
            raise ValueError("note_id must be a positive integer")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute("SELECT 1 FROM records WHERE id = ?", (record_id,)).fetchone()
            if record is None:
                raise KeyError(record_id)
            cursor = conn.execute(
                "DELETE FROM note_claims WHERE record_id = ? AND note_id = ?",
                (record_id, note_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(note_id)
            self._settle_pending_generations(conn, record_id)
            self._recalculate_record(conn, record_id)
            refreshed = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            return self._record_from_row(conn, refreshed)

    def queue_resend(self, record_id: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._expire_leases(conn, now)
            record = conn.execute("SELECT 1 FROM records WHERE id = ?", (record_id,)).fetchone()
            if record is None:
                raise KeyError(record_id)
            link_count = conn.execute(
                "SELECT COUNT(*) FROM note_claims WHERE record_id = ?", (record_id,)
            ).fetchone()[0]
            if link_count == 0:
                raise NoLinkedNotesError("record has no linked Anki notes")
            generation = conn.execute(
                """
                SELECT * FROM resend_generations
                WHERE record_id = ? AND state IN ('pending', 'leased')
                """,
                (record_id,),
            ).fetchone()
            coalesced = generation is not None
            if generation is None:
                cursor = conn.execute(
                    """
                    INSERT INTO resend_generations (
                        record_id, state, error, created_at, updated_at
                    ) VALUES (?, 'pending', '', ?, ?)
                    """,
                    (record_id, now, now),
                )
                generation = conn.execute(
                    "SELECT * FROM resend_generations WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO delivery_members (generation_id, note_id, initial_delivery)
                    SELECT ?, note_id, 0 FROM note_claims WHERE record_id = ?
                    """,
                    (generation["id"], record_id),
                )
                conn.execute(
                    """
                    UPDATE note_claims
                    SET delivery_state = 'pending', delivery_error = '', delivery_updated_at = ?
                    WHERE record_id = ?
                    """,
                    (now, record_id),
                )
                self._recalculate_record(conn, record_id)
            return {"generation": dict(generation), "coalesced": coalesced}

    def lease_resend(self, lease_seconds: int = 30) -> dict[str, Any] | None:
        if not 5 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 5 and 300")
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._expire_leases(conn, now)
            generation = conn.execute(
                """
                SELECT * FROM resend_generations
                WHERE state = 'pending'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if generation is None:
                return None
            token = secrets.token_urlsafe(24)
            expires_at = now + lease_seconds
            conn.execute(
                """
                UPDATE resend_generations
                SET state = 'leased', lease_token = ?, lease_expires_at = ?,
                    error = '', updated_at = ?
                WHERE id = ? AND state = 'pending'
                """,
                (token, expires_at, now, generation["id"]),
            )
            conn.execute(
                """
                UPDATE note_claims
                SET delivery_state = 'in_progress', delivery_error = '', delivery_updated_at = ?
                WHERE note_id IN (SELECT note_id FROM delivery_members WHERE generation_id = ?)
                    AND delivery_state IN ('pending', 'in_progress')
                """,
                (now, generation["id"]),
            )
            self._recalculate_record(conn, generation["record_id"])
            row = conn.execute(
                "SELECT * FROM records WHERE id = ?", (generation["record_id"],)
            ).fetchone()
            record = self._record_from_row(conn, row)
            members = conn.execute(
                """
                SELECT n.*, m.initial_delivery FROM note_claims n
                JOIN delivery_members m ON m.note_id = n.note_id
                WHERE m.generation_id = ? AND n.delivery_state = 'in_progress'
                ORDER BY n.created_at, n.note_id
                """,
                (generation["id"],),
            ).fetchall()
            record["linked_notes"] = [
                {**self._link_from_row(member), "initial_delivery": bool(member["initial_delivery"])}
                for member in members
            ]
            return {
                "generation_id": generation["id"],
                "lease_token": token,
                "lease_expires_at": expires_at,
                "record": record,
            }

    def renew_resend_lease(
        self,
        generation_id: int,
        lease_token: str,
        lease_seconds: int = 30,
    ) -> float:
        if not 5 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 5 and 300")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            generation = self._require_active_lease(conn, generation_id, lease_token)
            expires_at = time.time() + lease_seconds
            conn.execute(
                "UPDATE resend_generations SET lease_expires_at = ?, updated_at = ? WHERE id = ?",
                (expires_at, time.time(), generation["id"]),
            )
            return expires_at

    def adopt_media_targets(
        self,
        generation_id: int,
        lease_token: str,
        note_id: int,
        audio_field: str,
        image_field: str,
    ) -> dict[str, Any]:
        if note_id <= 0:
            raise ValueError("note_id must be a positive integer")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            generation = self._require_active_lease(conn, generation_id, lease_token)
            link = conn.execute(
                """
                SELECT n.* FROM note_claims n JOIN delivery_members m ON m.note_id = n.note_id
                WHERE n.record_id = ? AND n.note_id = ? AND m.generation_id = ?
                """,
                (generation["record_id"], note_id, generation_id),
            ).fetchone()
            if link is None:
                raise KeyError(note_id)
            stable_audio = link["audio_field"] or audio_field
            stable_image = link["image_field"] or image_field
            if link["audio_field"] and audio_field and link["audio_field"] != audio_field:
                raise ValueError("audio target is already stable")
            if link["image_field"] and image_field and link["image_field"] != image_field:
                raise ValueError("image target is already stable")
            conn.execute(
                """
                UPDATE note_claims
                SET audio_field = ?, image_field = ?, delivery_updated_at = ?
                WHERE record_id = ? AND note_id = ?
                """,
                (stable_audio, stable_image, time.time(), generation["record_id"], note_id),
            )
            refreshed = conn.execute(
                "SELECT * FROM note_claims WHERE record_id = ? AND note_id = ?",
                (generation["record_id"], note_id),
            ).fetchone()
            return self._link_from_row(refreshed)

    def report_resend_delivery(
        self,
        generation_id: int,
        lease_token: str,
        note_id: int,
        state: str,
        error: str = "",
    ) -> dict[str, Any]:
        if state not in {"done", "failed", "missing"}:
            raise ValueError("delivery state must be done, failed, or missing")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            generation = self._require_active_lease(conn, generation_id, lease_token)
            link = conn.execute(
                """
                SELECT 1 FROM note_claims n JOIN delivery_members m ON m.note_id = n.note_id
                WHERE n.record_id = ? AND n.note_id = ? AND m.generation_id = ?
                """,
                (generation["record_id"], note_id, generation_id),
            ).fetchone()
            if link is None:
                raise KeyError(note_id)
            if state == "missing":
                conn.execute(
                    "DELETE FROM note_claims WHERE record_id = ? AND note_id = ?",
                    (generation["record_id"], note_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE note_claims
                    SET delivery_state = ?, delivery_error = ?, delivery_updated_at = ?
                    WHERE record_id = ? AND note_id = ?
                    """,
                    (state, error, time.time(), generation["record_id"], note_id),
                )
            self._recalculate_record(conn, generation["record_id"])
            row = conn.execute(
                "SELECT * FROM records WHERE id = ?", (generation["record_id"],)
            ).fetchone()
            return self._record_from_row(conn, row)

    def finalize_resend(
        self,
        generation_id: int,
        lease_token: str,
        error: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            generation = self._require_active_lease(conn, generation_id, lease_token)
            fallback_error = error or "worker did not report delivery result"
            conn.execute(
                """
                UPDATE note_claims
                SET delivery_state = 'failed', delivery_error = ?, delivery_updated_at = ?
                WHERE note_id IN (SELECT note_id FROM delivery_members WHERE generation_id = ?)
                    AND delivery_state IN ('pending', 'in_progress')
                """,
                (fallback_error, now, generation_id),
            )
            conn.execute(
                """
                UPDATE resend_generations
                SET state = 'completed', lease_token = NULL, lease_expires_at = NULL,
                    error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error, now, generation_id),
            )
            self._queue_initial_deliveries(conn, generation["record_id"])
            self._recalculate_record(conn, generation["record_id"])
            row = conn.execute(
                "SELECT * FROM records WHERE id = ?", (generation["record_id"],)
            ).fetchone()
            return self._record_from_row(conn, row)

    def delete_record(self, record_id: str) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM note_claims WHERE record_id = ?", (record_id,))
            conn.execute("DELETE FROM resend_generations WHERE record_id = ?", (record_id,))
            cursor = conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
            if cursor.rowcount == 0:
                raise KeyError(record_id)
            conn.execute("DELETE FROM preview_requests WHERE record_id = ?", (record_id,))

    def clear_done_records(self) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                DELETE FROM note_claims
                WHERE record_id IN (SELECT id FROM records WHERE status = 'media_done')
                """
            )
            conn.execute(
                """
                DELETE FROM resend_generations
                WHERE record_id IN (SELECT id FROM records WHERE status = 'media_done')
                """
            )
            cursor = conn.execute("DELETE FROM records WHERE status = 'media_done'")
            conn.execute(
                """
                DELETE FROM preview_requests
                WHERE NOT EXISTS (
                    SELECT 1 FROM records WHERE records.id = preview_requests.record_id
                )
                """
            )
            return cursor.rowcount

    def clear_all_records(self) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM note_claims")
            conn.execute("DELETE FROM resend_generations")
            cursor = conn.execute("DELETE FROM records")
            conn.execute("DELETE FROM preview_requests")
            return cursor.rowcount

    def queue_preview(self, record_id: str) -> dict[str, Any]:
        record = self.get_record(record_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO preview_requests (id, record_id, created_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    record_id = excluded.record_id,
                    created_at = excluded.created_at
                """,
                (record_id, time.time()),
            )
        return record

    def consume_preview_request(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            request = conn.execute(
                "SELECT record_id FROM preview_requests WHERE id = 1"
            ).fetchone()
            if request is None:
                return None
            conn.execute("DELETE FROM preview_requests WHERE id = 1")
            record = conn.execute(
                "SELECT * FROM records WHERE id = ?", (request["record_id"],)
            ).fetchone()
            return self._record_from_row(conn, record) if record is not None else None
