"""Wrap nginx's output: redact in memory before Docker can persist any line."""

import json
import posixpath
import re
import signal
import subprocess
import sys
from urllib.parse import unquote

PATHS = re.compile(
    r'(/(?:users/log-in|book/restore)/)[^\s/?#"\'<>\\]+'
    r'|(/orders/[^\s/?#"\'<>\\]+/)[^\s/?#"\'<>\\]+', re.I
)
QUERY = re.compile(r'([^\s"\'<>\\]*/[^\s?"\'<>\\]*)\?[^\s"\'<>\\]*')
REFERRER = re.compile(r'(referrer: )"[^"\n]*"', re.I)
URLS = re.compile(r'(https?://[^\s/"\'<>\\]+)?(/[^\s"\'<>\\]*)', re.I)


def normalize_url(match):
    path, separator, _query = match[2].partition("?")
    # Nginx normalizes dot segments and repeated slashes before routing.
    path = "/" + posixpath.normpath("/" + path.lstrip("/")).lstrip("/")
    return (match[1] or "") + path + ("?[FILTERED]" if separator else "")


def redact(message):
    message = QUERY.sub(r'\1?[FILTERED]', message)
    for _ in range(3):
        decoded = unquote(message)
        if decoded == message:
            break
        message = decoded
    message = URLS.sub(normalize_url, message)
    message = PATHS.sub(lambda m: (m[1] or m[2]) + "[FILTERED]", message)
    message = QUERY.sub(r'\1?[FILTERED]', message)
    return REFERRER.sub(r'\1"[FILTERED]"', message)


def safe_record(raw):
    try:
        message = redact(raw.decode("utf-8", errors="replace").rstrip("\n"))
    except Exception:
        # Fail closed: neither raw input nor exception text is logged.
        message = "Log event withheld: credential redaction failed"
    return json.dumps({"nginx": message}, ensure_ascii=True)


def serve(args):
    # Nginx and its entrypoint never inherit Docker's log descriptors. Even
    # fallback/core errors go into this pipe. If PID 1 dies, Docker stops the
    # container; there is no unfiltered fallback log writer.
    child = subprocess.Popen(["/docker-entrypoint.sh", *args], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)

    def forward(signum, _frame):
        if child.poll() is None:
            child.send_signal(signum)

    for signum in (signal.SIGTERM, signal.SIGQUIT, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, forward)
    for raw in child.stdout:
        print(safe_record(raw), flush=True)
    return child.wait()


if __name__ == "__main__":
    sys.exit(serve(sys.argv[1:]))
