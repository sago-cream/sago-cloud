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
bun run deploy:sago-media-api
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
bun run install:media
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
minisago-worker.env
sago-media-api.env
obi.env
public-ingress.env
```

Production secrets are never committed. For Sago Media, copy
`env/sago-media-api.env.example` to `sago-media-api.env`.
Existing media installations require [the 2.0 migration](media-migration.md).

## MiniSago shared Drive connector

The dedicated `discord-drive` Google project and service account grant read-only
access to the 11 approved NTHUSA shared drives. Restore the complete JSON from
the encrypted attachment in the **discord-drive** entry at `safe.nthusa.tw`.
The account is `discord-drive@nthusa-discord-drive.iam.gserviceaccount.com`;
do not substitute an admin user's OAuth token or the Calendar service account.

Install compact, one-line JSON as `MINISAGO_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
in `/srv/sago-cloud/secrets/bot-core.env`. Keep that file mode 600; preserve all
unrelated values, including `MINISAGO_GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON`.
Write replacements atomically. JSON keeps PEM newlines escaped; do not place
literal private-key line breaks in the env file. Bot-core already loads this
file through Compose `env_file`, so no key belongs in a Compose file or Git.
Never add the credential to `minisago-worker.env` or the sandbox. The worker
receives only requested document bytes through the existing authenticated media
endpoint. Set `MINISAGO_GOOGLE_DRIVE_ACCESS=roles`; other values disable Drive
tools. The host checks fresh guild membership and matches current Google group
permissions to these Discord roles: 部長 `1514899497199861863`, 活動
`1514899497187147824`, 社群 `1514899497199861861`, 學權
`1514899497187147825`, 資訊 `1514899497187147822`. Their Google groups are
`sa-exec`, `sa-event`, `sa-media`, `sa-rights`, and `sa-it` at `nthusa.tw`, matched
by stable Google permission IDs in the application.

The server owner's chosen policy grants every member of guild
`1514899496797212683` access through active, readable **unmapped Google groups**,
including newly added unmapped groups. Individual-user, domain, and public-link
grants do not authorize Discord access. The bot owner has no role bypass.
Catalog entries, search results, direct reads, and cached media downloads
recheck Google permissions. Other guilds and DMs remain excluded. Only the
requester's roles are checked; replies appear in the invoking channel even
when other channel members lack those roles.

Deploy the merged MiniSago change only after its core and worker images pass.
Use MiniSago's `bun run deploy` from clean `main` matching `origin/main`; the
existing deployment helper updates core, Oracle worker, and Python sandbox.
The worker image supplies pypdf, python-docx, and openpyxl for PDF and Office
reads. Do not fast-forward or reset a dirty operations checkout as part of a
secret-only change. If images are already current and only the env changed,
recreate bot-core with the normal Compose deployment rather than merely
restarting it (restart does not reload env_file).

Verify `/api/health`, the connected worker, and these host-bound MCP operations:
list the approved drives, search a known drive for meeting minutes, read a
Google Doc, and fetch a PDF through request-local media for sandbox extraction.
Verify Drive tools are absent for a DM, another guild, and any access mode
other than `roles`. Check mapped department access, cross-department denial,
and unmapped-group access for a member without mapped roles. Revoke a role or
group grant and verify direct reads and cached media stop working. Log status
and counts only, never credentials or document contents. Google sharing and
the Discord role mapping jointly authorize access within the approved drives.

For recovery or rotation, restore the vault attachment, check its account and
project, install the replacement on the host, and verify search/read before
revoking the previous key. Keep Google's inherited service-account key-creation
restriction enforced outside an approved rotation window. The old admin OAuth
client and grant are not part of this connector. Keep a protected rollback copy
of bot-core.env during installation; after verification, remove temporary local
key downloads. Record deployment revision and verification date in the vault
entry so a later operator can restore the same configuration.

## Scheduled jobs

Install or refresh systemd units after changing the operations checkout:

```bash
scripts/install-health-watch-timer
scripts/install-docker-cleanup-timer
scripts/install-minisago-deploy-socket
scripts/install-public-ingress-timer
```

The health-watch installer copies the watcher and its shell dependency into a
content-addressed, root-owned release under
`/usr/local/libexec/sago-cloud-health-watch`, then activates it atomically.
Updating the repository does not change the root service's executable code
until this installation succeeds.

The watcher finds managed containers through the
`dev.hsichen.sago-cloud.managed=true` label, so it works across independent
Compose projects.

The MiniSago deployment socket accepts one immutable commit from the Oracle
worker, acknowledges it before the worker restarts, and deploys the matching
core and worker image tags as a socket-activated service. The request also
carries the originating Discord thread ID so the bot can report the terminal
result after restart. Requests cannot supply a command, path, image name, or
deployment target. Status and logs are stored under
`/srv/sago-cloud/state/minisago-deploy`.

Container logs rotate at 10 MB with three files retained per service.
The weekly Docker cleanup removes only unused images and build cache older than
30 days. It never prunes containers, networks, or volumes.

Obi notes are committed and pushed hourly from the Mac to the private
`sago-cream/obi` repository on `master`. MiniSago durable state is pulled from
Oracle five minutes past each hour into private `sago-cream/minisago-state`.
These are ordinary macOS cron jobs; no Codex automation is involved. Both require
the Mac to be awake and connected; MiniSago also requires Tailscale access.

MiniSago snapshots include guild-memory Markdown plus its Git history, reminders,
feature availability, PR-thread continuity and monitor cursors. They exclude media,
recordings, traces, sessions, caches, dependencies and workspaces. The memory repo
on Oracle deliberately has no remote; the separate backup checkout owns publishing.
The reader validates JSON and requires matching reads around its history capture,
retrying on concurrent changes without stopping services.

Current recovery secrets are in Bitwarden folder **Obi and MiniSago Recovery**.
See the private state repository README for restore instructions. Recover Obi by
cloning its `master` branch, rebuilding an empty CouchDB service, and uploading
from the recovered Mac vault before reconnecting other clients.

`sago-cloud-state-backup.timer` and `sago-cloud-restore-test.timer` were disabled
on 2026-09-09. `scripts/install-state-backup-timers` keeps them disabled by default;
set `ENABLE_LEGACY_VOLUME_BACKUPS=1` only to deliberately restore the old policy.
Media itself is expendable by user choice; this change does not delete live media.

Media prune and integrity timers run commands inside the published media image.
Install storage first; a successful media deployment enables the timers.

## Host access

Administrative SSH uses Tailscale. Configure the local `sago-cloud` SSH alias
to the VM's Tailscale MagicDNS name and verify it before deployment:

```bash
ssh sago-cloud
```

Do not expose TCP 22 in the OCI security list.

Obi's CouchDB port is bound only to host loopback. After its first deployment,
publish it inside the tailnet with Tailscale Serve:

```bash
sudo tailscale serve --bg http://127.0.0.1:5984
```

Use the HTTPS URL reported by Tailscale in Obsidian LiveSync. Do not create a
public DNS record or Cloudflare Tunnel ingress for Obi.

Install the versioned SSH policy with:

```bash
bun run install:ssh-hardening
```

The policy disables root login and X11 forwarding, allows only the `ubuntu`
account, and limits authentication attempts to three. The installer validates
the complete SSH configuration before reloading the service.
