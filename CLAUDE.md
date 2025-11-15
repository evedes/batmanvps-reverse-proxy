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
