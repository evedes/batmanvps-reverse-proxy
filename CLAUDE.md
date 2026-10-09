# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Docker-based Nginx reverse proxy for the Batman server that handles SSL termination and routing for multiple domains including eduardovedes.com.

## Architecture

- **nginx.conf**: Main Nginx configuration file that defines server blocks for each domain
- **docker-compose-reverseproxy.yaml**: Docker Compose configuration for the Nginx reverse proxy container
- **SSL certificates**: Mounted from ./ssl/{domain}/ directories containing fullchain.pem and privkey.pem files
- **External network**: Uses 'batmanvps' external Docker network to communicate with backend services

## Common Commands

```bash
# Start the reverse proxy
docker-compose -f docker-compose-reverseproxy.yaml up -d

# Stop the reverse proxy
docker-compose -f docker-compose-reverseproxy.yaml down

# View logs
docker-compose -f docker-compose-reverseproxy.yaml logs -f

# Restart Nginx (reload configuration)
docker-compose -f docker-compose-reverseproxy.yaml restart nginx

# Test Nginx configuration syntax
docker exec nginx-reverseproxy nginx -t
```

## Domain Configuration Pattern

Each domain follows this pattern in nginx.conf:

- HTTP (port 80): Redirects to HTTPS
- HTTPS (port 443): SSL termination with proxy_pass to backend services
- Backend services are accessed via Docker network names (e.g., `frontend-{domain}:3000`)
- API endpoints for some domains are routed to separate backend services on port 3001

## SSL Configuration

SSL certificates are expected in ./ssl/{domain}/ directories with:

- fullchain.pem (certificate chain)
- privkey.pem (private key)

All domains use TLSv1.2 and TLSv1.3 with HSTS headers for security.

## Umami Analytics

- `analytics.getkinfolio.com` serves the Umami dashboard from `batmanvps-umami:3000` (cert in `./ssl/getkinfolio.analytics/`; repo `batmanvps-umami`).
- Tracked sites (currently `getkinfolio.com`) expose exactly `/a/script.js` and `/a/api/send` through one anchored location, `location ~ ^/a/(script\.js|api/send)$`, proxied to Umami's `$umami_path` (the `map` at the top of nginx.conf). To track another site, copy that location into its HTTPS block. Never use a `/a/` prefix, because it would expose Umami's admin API on the site.
- Client IP: the location uses `set_real_ip_from <Cloudflare ranges>` + `real_ip_header CF-Connecting-IP`, scoped to that location, so `$remote_addr` is the visitor even behind Cloudflare, and a direct hit on batman cannot fake it. It then overwrites `X-Real-IP`, the only header Umami trusts (`CLIENT_IP_HEADER=x-real-ip`). Refresh the ranges from https://www.cloudflare.com/ips/ if Cloudflare changes them; a site not behind Cloudflare is unaffected.
- `logging/test_nginx.py` provisions a fake cert for every `ssl/` directory and asserts the Umami routing; add new cert directories there too.
