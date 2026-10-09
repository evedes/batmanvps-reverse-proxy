"""Exercise the repository's real nginx.conf in isolated local containers.

Run: python3 logging/test_nginx.py
Requires Docker, curl, openssl; uses throwaway certificates and no real accounts.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NGINX = "nginx:1.31-alpine"
CURL = "curlimages/curl:8.10.1"
# A real Cloudflare range, so a client on this network is "Cloudflare" to nginx.
CLOUDFLARE_SUBNET = "173.245.48.0/20"


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def wait_for(check):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if check():
            return
        threading.Event().wait(0.1)
    raise AssertionError("Timed out waiting for test container")


def main():
    prefix = "f10-" + uuid.uuid4().hex[:10]
    network = prefix + "-network"
    cf_network = prefix + "-cloudflare"
    upstream, umami, proxy = [prefix + suffix for suffix in ("-app", "-umami", "-proxy")]
    image = prefix + ":test"
    containers = []
    run("docker", "network", "create", network)
    try:
        run("docker", "build", "-t", image, str(ROOT / "logging"))
        with tempfile.TemporaryDirectory(prefix="f10-nginx-") as directory:
            base = Path(directory)
            os.chmod(base, 0o755)
            ssl_dir = base / "ssl"
            ssl_dir.mkdir()
            run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=localhost", "-keyout", str(base / "key"), "-out", str(base / "cert"))
            for domain in ("eduardovedes", "atomize", "minio", "zyker", "getkinfolio",
                           "getkinfolio.staging", "getkinfolio.analytics", "onedevarmy", "schola",
                           "bicodobra", "rhizo"):
                target = ssl_dir / domain
                target.mkdir()
                shutil.copy(base / "cert", target / "fullchain.pem")
                shutil.copy(base / "key", target / "privkey.pem")
            password_hash = run("openssl", "passwd", "-apr1", "test-only-password").strip()
            (ssl_dir / "getkinfolio.staging" / "htpasswd").write_text("edo:" + password_hash + "\n")
            mock = base / "upstream.conf"
            mock.write_text('events {} http { server { listen 4000; return 200 "$request_uri"; } }')
            run("docker", "run", "-d", "--name", upstream, "--network", network,
                "--network-alias", "getkinfolio", "--network-alias", "getkinfolio-staging",
                "-v", f"{mock}:/etc/nginx/nginx.conf:ro", NGINX)
            containers.append(upstream)
            umami_mock = base / "umami.conf"
            umami_mock.write_text('events {} http { server { listen 3000; '
                                  'return 200 "umami $request_uri $http_x_real_ip"; } }')
            run("docker", "run", "-d", "--name", umami, "--network", network,
                "--network-alias", "batmanvps-umami",
                "-v", f"{umami_mock}:/etc/nginx/nginx.conf:ro", NGINX)
            containers.append(umami)
            run("docker", "run", "-d", "--name", proxy, "--network", network,
                "-p", "127.0.0.1::80", "-p", "127.0.0.1::443",
                "-v", f"{ROOT / 'nginx.conf'}:/etc/nginx/conf.d/default.conf:ro",
                "-v", f"{ssl_dir}:/etc/nginx/ssl:ro", image)
            containers.append(proxy)
            wait_for(lambda: "start worker processes" in run("docker", "logs", proxy))
            run("docker", "exec", proxy, "nginx", "-t")
            ports = json.loads(run("docker", "inspect", proxy))[0]["NetworkSettings"]["Ports"]

            def request(host, path, https=True, auth=True, headers=(), data=None):
                port = ports["443/tcp" if https else "80/tcp"][0]["HostPort"]
                scheme = "https" if https else "http"
                args = ["curl", "--silent", "--show-error", "--insecure", "--path-as-is",
                        "--noproxy", "*", "--max-time", "10", "--resolve", f"{host}:{port}:127.0.0.1",
                        "-H", "Referer: https://getkinfolio.com/book/restore/F10_REFERRER_MARKER",
                        "-D", str(base / "headers"), "-w", "\n%{http_code}"]
                if auth:
                    basic = base64.b64encode(b"edo:test-only-password").decode()
                    args += ["-H", "Authorization: Basic " + basic]
                for header in headers:
                    args += ["-H", header]
                if data is not None:
                    args += ["--data", data]
                response = run(*args, f"{scheme}://{host}:{port}{path}")
                body, code = response.rsplit("\n", 1)
                assert 'Referrer-Policy: no-referrer' in (base / "headers").read_text()
                return body, int(code)

            paths = [
                "/users/log-in/F10_PATH_MARKER", "/book/restore/F10_PATH_MARKER",
                "/orders/K-000001/F10_PATH_MARKER/invoice",
                "/orders/K-000001/F10_PATH_MARKER/rate/5",
                "/print-files/id/interior?t=F10_QUERY_MARKER",
                "/checkout/return?token=F10_QUERY_MARKER",
                "/users/%6Cog-in/F10_PATH_MARKER",
                "//book//restore/F10_PATH_MARKER",
                "/book/unused/../restore/F10_PATH_MARKER",
            ]
            for host in ("getkinfolio.com", "staging.getkinfolio.com"):
                for path in paths:
                    body, status = request(host, path)
                    assert status == 200, (host, path, status)
                    assert "MARKER" in body, "Logging must not change the upstream credential"
            assert request("staging.getkinfolio.com", paths[0], auth=False)[1] == 401
            assert request("www.getkinfolio.com", paths[0])[1] == 301
            for host in ("getkinfolio.com", "www.getkinfolio.com", "staging.getkinfolio.com"):
                assert request(host, paths[1], https=False)[1] == 301
            assert request("getkinfolio.com", "/book/view")[1] == 200

            # Umami: only the two exact tracking paths reach it from a site origin,
            # rewritten to Umami's own paths; X-Real-IP cannot be spoofed.
            spoof = ("X-Real-IP: 203.0.113.9", "X-Forwarded-For: 203.0.113.9",
                     "CF-Connecting-IP: 203.0.113.9")
            body, status = request("getkinfolio.com", "/a/script.js", headers=spoof)
            assert status == 200 and body.startswith("umami /script.js "), body
            assert "203.0.113.9" not in body, "Client-supplied IP header reached Umami from a non-Cloudflare peer"
            # Through Cloudflare, CF-Connecting-IP becomes the visitor IP Umami sees.
            run("docker", "pull", "--quiet", CURL)
            run("docker", "network", "create", "--subnet", CLOUDFLARE_SUBNET, cf_network)
            run("docker", "network", "connect", cf_network, proxy)
            # Joining a network re-assigns the proxy's ephemeral host ports.
            ports.update(json.loads(run("docker", "inspect", proxy))[0]["NetworkSettings"]["Ports"])
            for path, target in (("/a/script.js", "/script.js"), ("/a/api/send", "/api/send")):
                body = run("docker", "run", "--rm", "--network", cf_network, CURL,
                           "--silent", "--insecure", "--max-time", "10",
                           "--connect-to", f"getkinfolio.com:443:{proxy}:443",
                           "-H", "CF-Connecting-IP: 198.51.100.7",
                           "-H", "X-Real-IP: 203.0.113.9",
                           f"https://getkinfolio.com{path}")
                assert body == f"umami {target} 198.51.100.7", (path, body)
            body, status = request("getkinfolio.com", "/a/api/send", data='{"type":"event"}')
            assert status == 200 and body.startswith("umami /api/send "), body
            for path in ("/a/login", "/a/api/auth/login", "/a/", "/a/script.js.map", "/a/api/send/x"):
                body, status = request("getkinfolio.com", path)
                assert status == 200 and body == path, (path, body)
            for host in ("staging.getkinfolio.com", "www.getkinfolio.com"):
                body, _ = request(host, "/a/script.js")
                assert not body.startswith("umami"), (host, body)
            body, status = request("analytics.getkinfolio.com", "/login")
            assert status == 200 and body.startswith("umami /login "), body
            assert request("analytics.getkinfolio.com", "/login", https=False)[1] == 301
            assert "Location: https://analytics.getkinfolio.com/login" in (base / "headers").read_text()

            run("docker", "kill", "--signal", "HUP", proxy)
            assert request("getkinfolio.com", "/book/view")[1] == 200

            # Force real nginx errors: request, upstream and referrer contexts must all be safe.
            run("docker", "stop", upstream)
            for path in paths:
                assert request("getkinfolio.com", path)[1] == 502
            wait_for(lambda: any(reason in run("docker", "logs", proxy) for reason in ("connect() failed", "could not be resolved", "upstream timed out")))
            logs = run("docker", "logs", proxy)
            assert any(reason in logs for reason in ("connect() failed", "could not be resolved", "upstream timed out"))
            assert '"status\\":502' in logs and '"status\\":200' in logs
            assert "/book/view" in logs and "request_id" in logs
            assert "[FILTERED]" in logs
            for marker in ("F10_PATH_MARKER", "F10_QUERY_MARKER", "F10_REFERRER_MARKER"):
                assert marker not in logs, "Secret reached redactor output: " + marker

            # Fallback/core stderr uses the same pipe; no raw file destination may leak.
            fallback = run("docker", "logs", proxy)
            fallback += run("docker", "exec", proxy, "find", "/var/log/nginx", "-type", "f",
                            "-exec", "cat", "{}", "+")
            for marker in ("F10_PATH_MARKER", "F10_QUERY_MARKER", "F10_REFERRER_MARKER"):
                assert marker not in fallback, "Secret reached nginx fallback logs: " + marker
            # A failed PID 1 cannot leave an unfiltered nginx running.
            run("docker", "kill", "--signal", "KILL", proxy)
            assert json.loads(run("docker", "inspect", proxy))[0]["State"]["Running"] is False
            print("PASS: nginx syntax, routing, umami tracking/dashboard, redirects, auth, access/error redaction, fail-closed lifecycle")
    finally:
        for container in reversed(containers):
            subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        subprocess.run(["docker", "image", "rm", image], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
        for name in (cf_network, network):
            subprocess.run(["docker", "network", "rm", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
