"""Expose a bounded Gmail read-only API on the socket provided by systemd."""

import base64
import json
import os
import re
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/"
TOKEN_URL = "https://oauth2.googleapis.com/token"
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def json_request(request):
    with build_opener(NoRedirect).open(request, timeout=12) as response:
        if response.status == 204:
            return {}
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Google response exceeds limit.")
    return json.loads(data)


class Gmail:
    def __init__(self, credential):
        self.credential = credential
        self.token = ""
        self.expires_at = 0

    def access(self):
        if time.monotonic() >= self.expires_at:
            form = self.credential | {"grant_type": "refresh_token"}
            result = json_request(Request(TOKEN_URL, data=urlencode(form).encode("ascii")))
            if set(result.get("scope", "").split()) != {SCOPE}:
                raise ValueError("Unexpected OAuth scope.")
            self.token = result["access_token"]
            self.expires_at = time.monotonic() + max(0, int(result["expires_in"]) - 45)
        return self.token

    def get(self, path, **params):
        headers = {"Authorization": "Bearer " + self.access()}
        return json_request(Request(GMAIL + path + "?" + urlencode(params), headers=headers))

    def status(self):
        profile = self.get("profile", fields="emailAddress")
        return {"connected": bool(profile["emailAddress"]), "scope": "gmail.readonly"}

    def search(self, query):
        result = self.get("messages", q=query, maxResults=10, fields="messages(id,threadId),nextPageToken")
        return {"messages": result.get("messages", []), "more": bool(result.get("nextPageToken"))}

    def read(self, message_id):
        result = self.get("messages/" + message_id, format="full", fields="id,snippet,payload")
        payload = result.get("payload", {})
        names = {"subject", "from", "to", "date"}
        headers = {
            header["name"].lower(): header["value"][:1000]
            for header in payload.get("headers", []) if header["name"].lower() in names
        }
        text = first_plain_text(payload)
        return {
            "id": result["id"], "headers": headers, "snippet": result.get("snippet", "")[:1000],
            "text": text[:12000], "truncated": len(text) > 12000,
        }


def first_plain_text(part):
    data = part.get("body", {}).get("data", "")
    if part.get("mimeType") == "text/plain" and not part.get("filename") and data:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    for child in part.get("parts", []):
        text = first_plain_text(child)
        if text:
            return text
    return ""


class GmailHandler(BaseHTTPRequestHandler):
    timeout = 5

    def log_message(self, *_):
        pass

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        try:
            params = parse_qs(url.query, max_num_fields=2)
            if url.path == "/status" and not params:
                result = self.server.gmail.status()
            elif url.path == "/search" and params.keys() == {"q"} and len(params["q"]) == 1:
                query = params["q"][0].strip()
                if not 1 <= len(query) <= 512:
                    raise ValueError("Invalid query.")
                result = self.server.gmail.search(query)
            elif url.path == "/read" and params.keys() == {"id"} and len(params["id"]) == 1:
                message_id = params["id"][0]
                if not MESSAGE_ID.fullmatch(message_id):
                    raise ValueError("Invalid Gmail message ID.")
                result = self.server.gmail.read(message_id)
            else:
                self.send_json(404, {"error": "unknown_operation"})
                return
        except HTTPError as exc:
            self.send_json(502, {"error": "google_api_error", "google_status": exc.code})
            return
        except json.JSONDecodeError:
            self.send_json(502, {"error": "google_response_not_json"})
            return
        except ValueError:
            self.send_json(400, {"error": "invalid_request"})
            return
        except (URLError, OSError, KeyError):
            self.send_json(502, {"error": "google_response_unavailable"})
            return
        self.send_json(200, result)

    def do_POST(self):
        self.send_json(405, {"error": "read_only"})


def main():
    if int(os.environ.get("LISTEN_FDS", "0")) != 1 or int(os.environ.get("LISTEN_PID", "0")) != os.getpid():
        raise RuntimeError("Expected one systemd socket.")
    path = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "gmail-grant"
    secret = json.loads(path.read_text())
    with HTTPServer(("127.0.0.1", 0), GmailHandler, bind_and_activate=False) as server:
        server.socket.close()
        server.socket = socket.socket(fileno=3)
        server.gmail = Gmail(secret)
        server.serve_forever()


if __name__ == "__main__":
    main()
