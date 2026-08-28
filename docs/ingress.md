# Cloudflare Ingress

Cloudflare Tunnel is the only public ingress path. Caddy has no published host
ports after cutover, while Tailscale remains the administrative path.

## Tunnel configuration

Create a locally managed Tunnel, then place its private files at:

```text
/srv/sago-cloud/secrets/cloudflared/config.yml
/srv/sago-cloud/secrets/cloudflared/credentials.json
```

Edit `config/routes.mjs`, then run `bun run generate:routing`. That one route
definition generates `edge/Caddyfile` and
`env/cloudflared.config.yml.example`; deployments reject stale generated files.
Route each public hostname to
`https://edge:443` and set `originServerName` to the matching public hostname so
Caddy's certificate is verified. `cloudflared` and Caddy share the private
frontend Docker network. No Tunnel identifier, credential, or provider token is
stored in this repository.

The media hostname is the deliberate exception: route it to `http://edge:80` on
the same private network. Cloudflare still terminates public HTTPS, while the
HTTP-only origin avoids a circular first-certificate bootstrap for a hostname
reachable exclusively through the Tunnel. Because Caddy has no published host
port, this origin is not reachable outside Docker.

Keep the directory traversable by the host deploy user and its files readable
only by the image's non-root user:

```bash
sudo chown ubuntu:65532 /srv/sago-cloud/secrets/cloudflared
sudo chmod 0710 /srv/sago-cloud/secrets/cloudflared
sudo chown 65532:65532 /srv/sago-cloud/secrets/cloudflared/{config.yml,credentials.json}
sudo chmod 0600 /srv/sago-cloud/secrets/cloudflared/{config.yml,credentials.json}
```

Deploy the Tunnel explicitly:

```bash
bun run deploy:cloudflared
```

## Caching and rate limits

Cache only immutable Homepage assets such as `/_next/static/*`. Explicitly
bypass `/api/*`, authenticated HTML, session-bearing responses, and private
wallpapers. Preserve the origin's `private` and `no-store` headers.

Use the single free rate-limit rule for both the Homepage wallpaper upload and
`POST media.hsichen.dev/v1/auth/device`. The production rule allows five
matching requests per IP every ten seconds, blocking bursts for ten seconds.
Authenticated media uploads retain their separate service quotas and
concurrency limit.

## Verification

Verify all public paths through Cloudflare:

```bash
HOMEPAGE_URL=https://homepage.example.com \
MEDIA_URL=https://media.example.com \
  scripts/verify-public-ingress
```

For continuous verification, copy `env/public-ingress.env.example` to
`/srv/sago-cloud/secrets/public-ingress.env`, set the two HTTPS origins and
their expected statuses, then run:

```bash
scripts/install-public-ingress-timer
```

The defaults expect `200` from Homepage and `404` from the media hostname root.
The timer checks both paths
every five minutes and records failures in the systemd journal. Cloudflare
Tunnel health notifications independently report connector degradation or
failure.

## Proxy trust

The edge trusts forwarding headers only from private-network peers, reads
`CF-Connecting-IP` before `X-Forwarded-For`, uses strict proxy-chain parsing,
and emits structured access logs for every public site. This is safe only while
Caddy remains unexposed and `cloudflared` is its sole public ingress.

After verifying the Tunnel from an external network, remove redundant OCI
ingress rules for TCP 80 and 443.
