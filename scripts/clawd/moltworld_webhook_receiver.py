#!/usr/bin/env python3
"""
MoltWorld webhook receiver: run on each agent host. When the backend (theebie) POSTs
new_chat, trigger one MoltWorld cron run so the agent can reply (event-driven).

Usage:
  CLAW=openclaw PORT=9999 python3 moltworld_webhook_receiver.py   # sparky2
  CLAW=clawdbot PORT=9999 python3 moltworld_webhook_receiver.py   # sparky1

Requires: CLAW (openclaw or clawdbot) in PATH. Expose this port to theebie (tunnel or same network).
Backend registers the URL via POST /admin/moltworld/webhooks with agent_id and url.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.getenv("PORT", "9999"))
CLAW = os.getenv("CLAW", "openclaw").strip() or "openclaw"
MOLTWORLD_CRON_JOB_ID = os.getenv("MOLTWORLD_CRON_JOB_ID", "").strip()


def get_moltworld_job_id() -> str:
    if MOLTWORLD_CRON_JOB_ID:
        return MOLTWORLD_CRON_JOB_ID
    try:
        out = subprocess.run(
            [CLAW, "cron", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        if out.returncode != 0:
            return ""
        for line in (out.stdout or "").splitlines():
            if "MoltWorld chat turn" in line:
                parts = line.split()
                if parts:
                    return parts[0]
    except Exception:
        pass
    return ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("[moltworld_webhook] %s\n" % (format % args))

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/", "/moltworld-trigger", "/moltworld_webhook"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}
        event = data.get("event") or ""
        if event != "new_chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "skipped": "not new_chat"}).encode())
            return
        job_id = get_moltworld_job_id()
        if not job_id:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "no_moltworld_cron_job"}).encode())
            return
        try:
            subprocess.run(
                [CLAW, "cron", "run", job_id, "--force"],
                capture_output=True,
                timeout=120,
                env={**os.environ, "PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "triggered": job_id}).encode())

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "claw": CLAW}).encode())
            return
        self.send_response(404)
        self.end_headers()


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print("MoltWorld webhook receiver listening on 0.0.0.0:%s (CLAW=%s)" % (PORT, CLAW), file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
