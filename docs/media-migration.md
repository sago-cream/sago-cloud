# Sago Media 2.0 migration

This is a coordinated, breaking rename across Sago Media and Sago Cloud.
Publish the Sago Media `v2.0.0` image first, then merge the infrastructure PR.
Do not use the regular deploy command to upgrade an existing 1.x installation.
The procedure below assumes the standard `/srv/sago-cloud` layout and the 10 GiB
loop filesystem. Stop if paths, mount source, or Compose project differ; adapt
and review the procedure for that installation before proceeding.

The API and public media hostnames do not change. Sago Drop needs no update.
Expect a maintenance window: stopping `edge` also interrupts other public sites
served by that Caddy instance. Keep the SSH session over Tailscale open.

## 1. Prepare before updating the operations checkout

Run on the VM, from the currently deployed checkout. Use a root shell so secrets
and backups never acquire public permissions. The backup directory must be new,
and the host needs enough free space for a complete copy of the media image.

```bash
sudo -i
set -euo pipefail
umask 077
cd /srv/sago-cloud/operations
migration=/srv/sago-cloud/state/media-rebrand-rollback
mkdir "$migration"
git rev-parse HEAD > "$migration/operations-commit"
test -z "$(git status --porcelain)"
test -f /srv/sago-cloud/state/pr-media.ext4
test -s /srv/sago-cloud/secrets/pr-media-api.env
test -d /srv/sago-cloud/backups/pr-media
test ! -e /srv/sago-media
test ! -e /srv/sago-cloud/state/sago-media.ext4
test ! -e /srv/sago-cloud/secrets/sago-media-api.env
test ! -e /srv/sago-cloud/backups/sago-media
findmnt --mountpoint /srv/pr-media
losetup -j /srv/sago-cloud/state/pr-media.ext4
df -h /srv/sago-cloud/state
# Confirm findmnt and losetup identify the same loop device before continuing.
docker pull ghcr.io/sago-cream/sago-media:v2.0.0
cp -a /etc/fstab "$migration/fstab"
cp -a /srv/sago-cloud/secrets/pr-media-api.env "$migration/pr-media-api.env"
cp -a /etc/systemd/system/sago-cloud-pr-media-* "$migration/"
cp -a /etc/systemd/system/docker.service.d/sago-cloud-pr-media-mount.conf "$migration/"
cp -a /usr/local/libexec/sago-cloud-pr-media-* "$migration/"
```

## 2. Quiesce writes and preserve the old filesystem

Disable timers and stop their service jobs before stopping the API, so pruning
or SQLite backups cannot race the snapshot. Keep the existing backup directory;
it will be renamed with its history intact.

```bash
systemctl disable --now sago-cloud-pr-media-{backup,prune,verify}.timer
systemctl stop sago-cloud-pr-media-{backup,prune,verify}.service
docker compose -f edge/compose.yaml down
docker compose -f services/pr-media-api/compose.yaml down
umount /srv/pr-media
cp --sparse=always /srv/sago-cloud/state/pr-media.ext4 "$migration/pr-media.ext4"
cmp /srv/sago-cloud/state/pr-media.ext4 "$migration/pr-media.ext4"
```

The offline image copy contains all media, pins, SQLite state, and its WAL. Do
not format a new filesystem or copy only the SQLite main file.

## 3. Rename state and configuration

```bash
mv /srv/sago-cloud/state/pr-media.ext4 /srv/sago-cloud/state/sago-media.ext4
mv /srv/pr-media /srv/sago-media
if [ -d /srv/sago-cloud/backups/pr-media ]; then
  mv /srv/sago-cloud/backups/pr-media /srv/sago-cloud/backups/sago-media
fi
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/fstab')
s = p.read_text()
old = '/srv/sago-cloud/state/pr-media.ext4 /srv/pr-media '
assert s.count(old) == 1, 'Expected exactly one standard media mount entry'
p.write_text(s.replace(old, '/srv/sago-cloud/state/sago-media.ext4 /srv/sago-media '))
p = Path('/srv/sago-cloud/secrets/pr-media-api.env')
s = p.read_text()
# Only environment keys and known product paths/commands change. Preserve secrets.
lines = []
for line in s.splitlines():
    key, sep, value = line.partition('=')
    if key.startswith('PR_MEDIA_'):
        key = key.replace('PR_MEDIA_', 'MEDIA_', 1)
        if key.endswith('_COMMAND') or key == 'MEDIA_ROOT':
            value = value.replace('pr-media', 'sago-media')
    if key == 'MEDIA_STATE_DIR':
        value = value.replace('/srv/pr-media', '/srv/sago-media')
    if key == 'MEDIA_IMAGE':
        value = 'ghcr.io/sago-cream/sago-media:v2.0.0'
    lines.append(key + sep + value)
keys = [line.split('=', 1)[0] for line in lines if '=' in line and not line.startswith('#')]
assert len(keys) == len(set(keys)), 'Resolve duplicate environment keys before migrating'
p.write_text('\n'.join(lines) + '\n')
p.rename('/srv/sago-cloud/secrets/sago-media-api.env')
PY
e2label /srv/sago-cloud/state/sago-media.ext4 sago-media
mount /srv/sago-media
findmnt --mountpoint /srv/sago-media
```

Any custom provisioning environment must also replace `PR_MEDIA_ROOT` and
`PR_MEDIA_SIZE_BYTES` with `MEDIA_ROOT` and `MEDIA_SIZE_BYTES`; the old
`PR_MEDIA_IMAGE` storage-file override becomes `MEDIA_STORAGE_IMAGE`.
`MEDIA_IMAGE` is reserved for the container image. Remove the retired
`PR_MEDIA_BASE_URL` line from `minisago-worker.env` if present; the worker no
longer consumes that setting.

## 4. Install and deploy the new release

Update the operations checkout to the merged main branch. Remove the old unit
files and installed helpers only after their copies are safely in the rollback
directory. The new installer reuses the existing filesystem, without formatting
it. No Docker daemon restart is required.

```bash
git switch main
git pull --ff-only
rm /etc/systemd/system/sago-cloud-pr-media-{backup,prune,verify}.{service,timer}
rm /etc/systemd/system/docker.service.d/sago-cloud-pr-media-mount.conf
rm /usr/local/libexec/sago-cloud-pr-media-{backup,maintenance}
scripts/install-sago-media-storage
scripts/deploy-sago-media-api
scripts/deploy-edge
scripts/backup-sago-media-state
scripts/verify-state-backups
scripts/status
systemctl status sago-cloud-media-{backup,prune,verify}.timer
```

Verify an existing share URL, an existing device upload, GitHub login, and the
admin dashboard. Check Docker lists only the new `sago-cloud-media-api` project
for media and Caddy reaches `sago-media-api:3000`. Keep the rollback snapshot
until these checks and a subsequent scheduled backup succeed. Only then remove
it according to the normal backup retention policy.

## Rollback

In a new root shell, first set
`migration=/srv/sago-cloud/state/media-rebrand-rollback` and change directory to
`/srv/sago-cloud/operations`.

If a step fails, keep writes stopped and use the snapshot. Restoring it discards
uploads and authentication changes made after the snapshot; preserve the new
image first if the new service accepted traffic. These commands assume step 4
was reached; if it was not, skip stopping or removing new components that do not
exist. Do not run the old and new APIs together.

```bash
systemctl disable --now sago-cloud-media-{backup,prune,verify}.timer
systemctl stop sago-cloud-media-{backup,prune,verify}.service
docker compose -f edge/compose.yaml down
docker compose -f services/sago-media-api/compose.yaml down
umount /srv/sago-media
mv /srv/sago-cloud/state/sago-media.ext4 "$migration/failed-sago-media.ext4"
cp --sparse=always "$migration/pr-media.ext4" /srv/sago-cloud/state/pr-media.ext4
mv /srv/sago-media /srv/pr-media
cp -a "$migration/fstab" /etc/fstab
cp -a "$migration/pr-media-api.env" /srv/sago-cloud/secrets/pr-media-api.env
mv /srv/sago-cloud/secrets/sago-media-api.env "$migration/failed-sago-media-api.env"
if [ -d /srv/sago-cloud/backups/sago-media ]; then
  mv /srv/sago-cloud/backups/sago-media /srv/sago-cloud/backups/pr-media
fi
rm /etc/systemd/system/sago-cloud-media-{backup,prune,verify}.{service,timer}
rm /etc/systemd/system/docker.service.d/sago-cloud-media-mount.conf
rm /usr/local/libexec/sago-cloud-media-{backup,maintenance}
cp -a "$migration"/sago-cloud-pr-media-*.service /etc/systemd/system/
cp -a "$migration"/sago-cloud-pr-media-*.timer /etc/systemd/system/
cp -a "$migration/sago-cloud-pr-media-mount.conf" /etc/systemd/system/docker.service.d/
cp -a "$migration/sago-cloud-pr-media-backup" "$migration/sago-cloud-pr-media-maintenance" /usr/local/libexec/
mount /srv/pr-media
systemctl daemon-reload
git switch --detach "$(cat "$migration/operations-commit")"
scripts/deploy-pr-media-api
scripts/deploy-edge
```

Repeat the share, login, and upload checks after rollback. Return the operations
checkout to main only when a corrected upgrade is ready.
