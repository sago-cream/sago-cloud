# Sago Cloud

Infrastructure and deployment tooling for a shared Oracle ARM64 host.
Applications run as independent Docker Compose stacks behind Caddy and a
Cloudflare Tunnel.

## Services

| Stack | Role |
| --- | --- |
| `bot-core` | [MiniSago](https://github.com/sago-cream/mini-sago) Discord bot |
| `minisago-worker` | Always-on Codex worker |
| `pr-media-api` | [Sago Media](https://github.com/sago-cream/sago-media) backend |
| `homepage` | [Homepage](https://github.com/sago-cream/homepage) app SSR |
| `obi` | CouchDB for Obsidian LiveSync |
| `edge` | Caddy routing and media serving |
| `cloudflared` | Outbound-only public ingress |

## Documentation

- [Architecture](docs/architecture.md) — host layout, stacks, networks, images,
  and worker boundaries
- [Deployment and operations](docs/operations.md) — deployment targets, setup,
  secrets, scheduled jobs, backups, and host access
- [Cloudflare ingress](docs/ingress.md) — Tunnel configuration, caching,
  verification, and proxy trust
- [Media deployment](docs/pr-media.md) — image, storage, routing, secrets, and
  maintenance schedules
- [Migration and rollback](docs/migration.md) — legacy namespace migration,
  host rename, and post-rollback cleanup
