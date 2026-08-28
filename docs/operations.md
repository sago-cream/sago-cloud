# Deployment and Operations

## Deployments

Run deployments from this repository:

```bash
bun run deploy:all
bun run deploy:edge
bun run deploy:cloudflared
bun run deploy:bot-core
bun run deploy:minisago
bun run deploy:minisago-worker
bun run deploy:pr-media-api
bun run deploy:homepage
bun run deploy:obi
bun run status
```

`deploy:all` manages the regular stacks. Cloudflare Tunnel deploys separately.
`deploy:minisago` and `deploy:proxy` remain compatibility aliases.

Application repositories wait for their image workflows and then invoke the
matching remote deployment. This repository's deployment command requires a
clean local `main` that matches `origin/main`, fast-forwards the VM checkout,
and runs the selected stack command. It never pushes code.

## Initial host setup

Clone this repository to `/srv/sago-cloud/operations`, then install the runtime
layout:

```bash
scripts/install-layout
```

This creates the runtime symlinks, Docker networks, and external volumes. Media
requires its own provisioning step before its API stack starts:

```bash
bun run install:pr-media
```

See [Cloudflare ingress](ingress.md) before deploying the Tunnel.

## Secrets

Create production files from `env/*.env.example` under
`/srv/sago-cloud/secrets`:

```text
proxy.env
cloudflared/config.yml
cloudflared/credentials.json
bot-core.env
homepage.env
minisago-worker.env
pr-media-api.env
obi.env
public-ingress.env
```

Production secrets are never committed.

## Scheduled jobs

Install or refresh systemd units after changing the operations checkout:

```bash
scripts/install-health-watch-timer
scripts/install-docker-cleanup-timer
scripts/install-public-ingress-timer
scripts/install-state-backup-timers
```

The health-watch installer copies the watcher and its shell dependency into a
content-addressed, root-owned release under
`/usr/local/libexec/sago-cloud-health-watch`, then activates it atomically.
Updating the repository does not change the root service's executable code
until this installation succeeds.

The watcher finds managed containers through the
`dev.hsichen.sago-cloud.managed=true` label, so it works across independent
Compose projects.

Container logs rotate at 10 MB with three files retained per service.
The weekly Docker cleanup removes only unused images and build cache older than
30 days. It never prunes containers, networks, or volumes.

Bot and CouchDB volume backups run daily with the affected stack briefly
stopped for a consistent snapshot. A weekly restore test imports the newest
archives into disposable volumes and starts CouchDB against the restored data.
Off-host copies are made separately; no cloud-storage subscription or
credential is required by this repository.

Media prune and integrity timers run commands inside the published media image.
Install storage first; a successful media deployment enables the timers.

## Host access

Administrative SSH uses Tailscale. Configure the local `sago-cloud` SSH alias
to the VM's Tailscale MagicDNS name and verify it before deployment:

```bash
ssh sago-cloud
```

Do not expose TCP 22 in the OCI security list.

Install the versioned SSH policy with:

```bash
bun run install:ssh-hardening
```

The policy disables root login and X11 forwarding, allows only the `ubuntu`
account, and limits authentication attempts to three. The installer validates
the complete SSH configuration before reloading the service.
