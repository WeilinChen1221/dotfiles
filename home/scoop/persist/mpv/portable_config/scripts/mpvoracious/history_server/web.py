from __future__ import annotations

import argparse
import json
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .store import (
    HistoryStore,
    InvalidStatusError,
    NoLinkedNotesError,
    StaleLeaseError,
)


PROTOCOL_VERSION = 2
ASSET_DIR = Path(__file__).with_name("assets")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/history.css": ("history.css", "text/css; charset=utf-8"),
    "/assets/history.js": ("history.js", "text/javascript; charset=utf-8"),
}


class HistoryHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], store: HistoryStore) -> None:
        super().__init__(server_address, HistoryRequestHandler)
        self.store = store


class HistoryRequestHandler(BaseHTTPRequestHandler):
    server: HistoryHTTPServer

    @property
    def store(self) -> HistoryStore:
        return self.server.store

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ASSETS:
            filename, content_type = ASSETS[parsed.path]
            self._send_asset(filename, content_type)
        elif parsed.path == "/health":
            self._send_json({"ok": True, "service": "mpvoracious-history", "protocol_version": PROTOCOL_VERSION})
        elif parsed.path == "/api/records":
            self._handle_list_records(parsed.query)
        elif parsed.path == "/api/pending":
            self._handle_pending(parsed.query)
        elif parsed.path == "/api/preview":
            self._send_json({"record": self.store.consume_preview_request()})
        else:
            self._send_not_found()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/records":
            self._handle_create_record()
            return
        if parsed.path == "/api/discovery":
            self._handle_discovery()
            return
        if parsed.path == "/api/claims":
            self._handle_claim()
            return
        if parsed.path == "/api/records/clear-done":
            self._send_json({"deleted": self.store.clear_done_records()})
            return
        if parsed.path == "/api/records/clear-all":
            self._send_json({"deleted": self.store.clear_all_records()})
            return
        if parsed.path == "/api/resends/lease":
            self._handle_lease_resend()
            return

        generation_id, action = self._parse_resend_action(parsed.path)
        if generation_id is not None:
            if action == "renew":
                self._handle_renew_resend(generation_id)
            elif action == "targets":
                self._handle_adopt_targets(generation_id)
            elif action == "result":
                self._handle_resend_result(generation_id)
            elif action == "complete":
                self._handle_finalize_resend(generation_id)
            else:
                self._send_not_found()
            return

        record_id, action = self._parse_record_action(parsed.path)
        if record_id is not None and action == "status":
            self._handle_update_status(record_id)
        elif record_id is not None and action == "missing-note":
            self._handle_remove_missing_note(record_id)
        elif record_id is not None and action == "resend":
            self._handle_queue_resend(record_id)
        elif record_id is not None and action == "preview":
            self._handle_queue_preview(record_id)
        else:
            self._send_not_found()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        record_id = self._parse_record_id(parsed.path)
        if record_id is None:
            self._send_not_found()
            return
        try:
            self.store.delete_record(record_id)
        except KeyError:
            self._send_not_found()
            return
        self._send_json({"deleted": 1})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_list_records(self, query: str) -> None:
        params = parse_qs(query, keep_blank_values=True)
        statuses = [value for value in params.get("status", []) if value]
        profiles = [value for value in params.get("profile", []) if value]
        source_info = params.get("source_info", [""])[0]
        subtitle = params.get("subtitle", [""])[0]
        try:
            note_value = params.get("note_id", [""])[0]
            note_id = int(note_value) if note_value else None
            page = self.store.list_records(
                statuses=statuses,
                source_info=source_info,
                subtitle=subtitle,
                profiles=profiles,
                note_id=note_id,
            )
        except (InvalidStatusError, TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(page)

    def _handle_pending(self, query: str) -> None:
        params = parse_qs(query)
        normalized_sentence = params.get("normalized_sentence", [""])[0]
        try:
            window_minutes = int(params.get("window_minutes", ["120"])[0])
        except ValueError:
            window_minutes = 120
        record = self.store.find_pending_by_normalized_sentence(
            normalized_sentence, window_minutes
        )
        self._send_json({"record": record})

    def _handle_create_record(self) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            record = self.store.add_record(payload)
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(record, HTTPStatus.CREATED)

    def _handle_claim(self) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            result = self.store.claim_note(
                note_id=int(payload["note_id"]),
                normalized_sentence=str(payload["normalized_sentence"]),
                window_minutes=int(payload["window_minutes"]),
                profile=str(payload.get("profile", "")),
                audio_field=str(payload.get("audio_field", "")),
                image_field=str(payload.get("image_field", "")),
                note_created_at=payload.get("note_created_at"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result)

    def _handle_update_status(self, record_id: str) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            note_id = payload.get("note_id")
            if note_id is not None:
                note_id = int(note_id)
            record = self.store.update_status(
                record_id,
                status=str(payload.get("status", "")),
                note_id=note_id,
                error=str(payload.get("error", "")),
            )
        except KeyError:
            self._send_not_found()
            return
        except (InvalidStatusError, TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(record)

    def _handle_queue_resend(self, record_id: str) -> None:
        try:
            result = self.store.queue_resend(record_id)
        except KeyError:
            self._send_not_found()
            return
        except NoLinkedNotesError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        self._send_json(result, HTTPStatus.ACCEPTED)

    def _handle_remove_missing_note(self, record_id: str) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            record = self.store.remove_missing_note(record_id, int(payload["note_id"]))
        except KeyError:
            self._send_not_found()
            return
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"record": record})

    def _handle_lease_resend(self) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            lease_seconds = int(payload.get("lease_seconds", 30))
            lease = self.store.lease_resend(lease_seconds)
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"lease": lease})

    def _handle_renew_resend(self, generation_id: int) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            expires_at = self.store.renew_resend_lease(
                generation_id,
                str(payload.get("lease_token", "")),
                int(payload.get("lease_seconds", 30)),
            )
        except StaleLeaseError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"lease_expires_at": expires_at})

    def _handle_adopt_targets(self, generation_id: int) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            link = self.store.adopt_media_targets(
                generation_id,
                str(payload.get("lease_token", "")),
                int(payload["note_id"]),
                str(payload.get("audio_field", "")),
                str(payload.get("image_field", "")),
            )
        except StaleLeaseError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except KeyError:
            self._send_not_found()
            return
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"link": link})

    def _handle_resend_result(self, generation_id: int) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            record = self.store.report_resend_delivery(
                generation_id,
                str(payload.get("lease_token", "")),
                int(payload["note_id"]),
                str(payload.get("state", "")),
                str(payload.get("error", "")),
            )
        except StaleLeaseError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except KeyError:
            self._send_not_found()
            return
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"record": record})

    def _handle_finalize_resend(self, generation_id: int) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            record = self.store.finalize_resend(
                generation_id,
                str(payload.get("lease_token", "")),
                str(payload.get("error", "")),
            )
        except StaleLeaseError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        self._send_json({"record": record})

    def _handle_queue_preview(self, record_id: str) -> None:
        try:
            record = self.store.queue_preview(record_id)
        except KeyError:
            self._send_not_found()
            return
        self._send_json({"record": record})

    @staticmethod
    def _parse_record_id(path: str) -> str | None:
        prefix = "/api/records/"
        if not path.startswith(prefix):
            return None
        suffix = path[len(prefix) :]
        return unquote(suffix) if suffix and "/" not in suffix else None

    @staticmethod
    def _parse_record_action(path: str) -> tuple[str | None, str | None]:
        prefix = "/api/records/"
        if not path.startswith(prefix):
            return None, None
        parts = path[len(prefix) :].split("/")
        if len(parts) != 2 or not all(parts):
            return None, None
        return unquote(parts[0]), parts[1]

    @staticmethod
    def _parse_resend_action(path: str) -> tuple[int | None, str | None]:
        prefix = "/api/resends/"
        if not path.startswith(prefix):
            return None, None
        parts = path[len(prefix) :].split("/")
        if len(parts) != 2 or not all(parts):
            return None, None
        try:
            generation_id = int(parts[0])
        except ValueError:
            return None, None
        return generation_id, parts[1]

    def _read_json(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return None
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _send_asset(self, filename: str, content_type: str) -> None:
        data = (ASSET_DIR / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _handle_discovery(self) -> None:
        payload = self._read_json()
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            timestamp = payload.get("scanned_through")
            cursor = self.store.discovery_cursor(
                str(payload.get("scope", "")),
                int(timestamp) if timestamp is not None else None,
            )
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"scanned_through": cursor})

    def _send_json(
        self,
        body: dict[str, Any] | list[Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_not_found(self) -> None:
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def make_server(host: str, port: int, store: HistoryStore) -> ThreadingHTTPServer:
    return HistoryHTTPServer((host, port), store)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve mpvoracious mining history")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=44765)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()
    log = args.log_file.open("w", encoding="utf-8") if args.log_file else None
    server = None
    try:
        store = HistoryStore(args.db)
        server = make_server(args.host, args.port, store)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=log or sys.stderr)
        raise SystemExit(1)
    finally:
        if server is not None:
            server.server_close()
        if log is not None:
            log.close()


if __name__ == "__main__":
    main()
