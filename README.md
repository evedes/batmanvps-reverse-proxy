# batman-reverse-proxy

A Docker-based Nginx reverse proxy for the Batman dedicated server that handles SSL termination and routing for eduardovedes.com and its subdomains.

## Umami analytics

The Umami dashboard is served at `analytics.getkinfolio.com` (certificate in
`ssl/getkinfolio.analytics/`), proxied to the `batmanvps-umami` container (repository
`batmanvps-umami`, deployed from Forgejo). Tracked sites serve the tracker first-party through
one anchored location, `location ~ ^/a/(script\.js|api/send)$` (exactly those two paths, mapped to
Umami's by `$umami_path`), currently on `getkinfolio.com` only. To track another site, copy that
location into its HTTPS server block. Never use a `/a/` prefix location, because that would expose
Umami's login and admin API on the site. Because getkinfolio.com is behind Cloudflare, the location takes the visitor IP from
`CF-Connecting-IP`, but only for connections from Cloudflare's published ranges (`set_real_ip_from`).
It then overwrites `X-Real-IP`, the only header Umami reads, so visitors cannot spoof their location.

## Kinfolio credential-safe logging

Kinfolio's login, restore and order URLs carry access credentials. Its production/staging,
HTTP and www redirect logs use `credential_safe`: method, sanitized path, status, bytes,
request ID and request/upstream durations. Queries, referrers, user agents, basic-auth usernames
and cookies are omitted. The proxy forwards its generated request ID to Kinfolio for correlation.
These virtual hosts also send `Referrer-Policy: no-referrer`.

Nginx error messages can repeat the raw request, upstream URL and referrer and do not support
access-log formatting. `logging/Dockerfile` builds nginx 1.31 Alpine with Python's standard
library. Its entrypoint runs nginx with stdout and stderr piped through `logging/redactor.py`
**before Docker can persist them**, including core/fallback errors. It normalizes encoded
paths, repeated slashes and dot segments, masks credentials, removes query/referrer contents,
and emits JSON. A redaction error emits a fixed diagnostic without the raw input or exception.
If this PID 1 dies, the container stops; nginx cannot keep serving with an unfiltered logger.
TERM/QUIT/INT/HUP are forwarded to nginx so shutdown and reload still work.

Read these records with `docker logs nginx-reverseproxy`; the host field distinguishes
production and staging. Docker rotates at **10 MB × 5 files**. Docker/host administrators can
read these logs. Other sites with explicit file logs retain those destinations.

Legacy Kinfolio `/var/log/nginx/getkinfolio*.log` files are no longer written by this
configuration. Before the first replacement, the deployment workflow archives existing files
under `~/.local/state/kinfolio-legacy-proxy-logs/` (directories 0700, files 0600) to preserve audit
evidence. These restricted archives still contain historical credentials; do not publish them.
Archive removal is explicit and their retention remains an operator decision. At inspection,
the running container's old files were mode 0644; its logrotate config specified daily rotation
with 52 copies, but a scheduled logrotate invocation was not established. Those settings must
not be mistaken for verified retention. The new container's Docker rotation is explicit.

The workflow tests redaction, builds the proxy image, validates nginx with the deployed mounts,
archives the legacy logs, and then starts/reloads nginx. **Deploy both this repository and the
Kinfolio application change**: neither side alone fixes both logging boundaries.

Deploys are serialized and stop on the first error. Before replacing files, the workflow saves
the active configuration, image ID and container-local logs under
`~/.local/state/reverseproxy-rollback/<commit>/` with owner-only permissions, and tags the old
image `batman-reverseproxy:rollback-<commit>`. No server-wide image cleanup runs. The workflow
checks production and staging health through the local TLS proxy after replacement. Replacing
the shared proxy (every deploy recreates the container, because `nginx.conf` is a single-file
bind mount that a running container would keep pinned to the old file) briefly interrupts existing connections; it does not restart application
containers. A rollback uses the saved configuration and image, followed by `nginx -t` and the
same origin health checks. Saved logs are sensitive and must remain restricted.

Validation (Docker, Python 3, curl and openssl required; no live credentials/services):

```sh
python3 -m unittest discover -s logging -p 'test_redactor.py'
python3 logging/test_nginx.py
docker compose -f docker-compose-reverseproxy.yaml config --quiet
```

The integration test uses this repository's actual nginx.conf, disposable certificates and
isolated containers. It checks normal requests, signed paths/queries, basic-auth failures,
redirects, forced upstream failures, encoded paths, reload and fail-closed process termination.
Temporary containers, network, image and certificates are removed afterwards.
