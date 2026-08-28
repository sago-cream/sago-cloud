# Architecture

Sago Cloud is the runtime wiring for a shared Oracle ARM64 compute host.
Resources are named by role so applications can be renamed, replaced, or split
without changing the host, edge network, deployment tooling, or backup layout.

## Host layout

```text
/srv/sago-cloud/
  operations/          # this repository
  edge/                 # symlink to operations/edge
  services/             # symlink to operations/services
  jobs/                 # symlink to operations/jobs
  secrets/              # production env files, never committed
  backups/
  state/
/srv/pr-media/          # dedicated, bounded PR-media filesystem
```

Run `scripts/install-layout` after cloning this repository to
`/srv/sago-cloud/operations`. It creates the runtime links, the
`sago_cloud_edge` frontend network, the isolated `sago_cloud_data` database
network, and external volumes.

## Runtime stacks

Each workload is an independent Docker Compose project:

- `edge` provides Caddy routing and serves Sago Media files.
- `cloudflared` provides outbound-only Cloudflare Tunnel ingress. It deploys
  separately so a configuration merge cannot cut over live traffic.
- `bot-core` runs the MiniSago Discord bot.
- `minisago-worker` runs one always-on `chat,dev` Codex worker.
- `pr-media-api` deploys the versioned `ghcr.io/sago-cream/sago-media` product image. It
  has no published host port and no application source in this repository.
- `homepage` runs the ARM64 Homepage image. Authentication, bookmarks, and
  private wallpaper storage live in Supabase.
- `obi` runs CouchDB for Obsidian LiveSync. Its host port is loopback-only and
  Tailscale Serve provides HTTPS access inside the tailnet.

Public services attach to `sago_cloud_edge`. Caddy discovers services through role-based network aliases;
`/bot/*` is the neutral bot route and `/` routes to `bot-core`.

The co-located worker reaches `bot-core` through its private frontend-network
alias instead of public-IP hairpin routing.

## Worker boundaries

The worker mounts one repo-scoped GitHub login, a broker secret, persistent
Codex and worker state, and a disposable workspace. Media uploads go through
the authenticated public API; the worker does not mount media storage.

The broker binds the worker secret to `oracle`/`chat,dev`, while Codex restricts
each job to its selected checkout. Only owner requests can route to Sol. Remote
mutation requires an explicit owner request, protected branches reject direct
and force pushes, and provider credentials are not mounted.

Codex runs job commands through Bubblewrap. The worker keeps Docker's default
seccomp allowlist, with only Bubblewrap's namespace and mount setup syscalls
added, and uses a dedicated AppArmor profile derived from Docker's default
container profile. The deployment installs that profile before recreating the
worker; it does not disable either host security mechanism or grant the worker
Linux capabilities. The vendored seccomp baseline is Moby `seccomp/v0.2.1`.

## Images

Application repositories build Linux ARM64 images on native ARM64 GitHub
Actions runners and publish `main` and immutable `sha-<commit>` tags:

```text
ghcr.io/sago-cream/minisago
ghcr.io/sago-cream/minisago-worker
ghcr.io/sago-cream/homepage
ghcr.io/sago-cream/sago-media
```

The VM only pulls images and starts containers; it does not clone or build
application source. Before the first private image pull, authenticate Docker on
the VM with a GitHub token limited to `read:packages`.
