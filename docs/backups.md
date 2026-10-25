# Private database backups

Obi stays on its hourly Mac Git job. MiniSago durable JSON/Markdown stays on its
hourly Oracle Git job, with monitor timestamp-only changes suppressed. Database
credentials use a separate recovery path and never enter Git.

## Schedule and destinations

| Data | Oracle snapshot | Off-host copy |
| --- | --- | --- |
| Sago Media authentication SQLite | `sago-cloud-media-backup.timer`, daily 00:00–00:30 UTC (08:00–08:30 Taipei) | Recovery Mac, `~/Library/Application Support/SagoCloud/backups/sago-media/` |
| MiniSago encrypted mail credentials | `sago-cloud-mail-backup.timer`, same daily window | Recovery Mac, `~/Library/Application Support/SagoCloud/backups/minisago-mail/` |

Oracle copies live databases without stopping services. Media uses SQLite
serialization and an integrity check. Mail reads the encrypted `credentials`
table into a new SQLite database; invitations, OAuth flows and browser receipts
are excluded. The mail encryption key and OAuth client secret remain separate in
Bitwarden/Vaultwarden. The backup does not decrypt credentials.

Oracle backups are root-owned, directories mode 700 and files mode 600. Each new
snapshot is published by rename after it is complete. The Mac uses the same
private modes and FileVault protection. Both destinations retain about 30 days;
Mac expiration uses the original snapshot date. Media files are still expendable.

## Install

On Oracle, run from the reviewed infrastructure checkout:

```bash
scripts/install-private-backup-timers
sudo systemctl start sago-cloud-mail-backup.service sago-cloud-media-backup.service
```

The installer refreshes the media backup executable, installs the mail timer and
a root-owned read-only export command. It does not recreate containers or change
the retired bot/CouchDB snapshot policy. Existing media storage provisioning owns
the media timer; verify it is enabled after a successful media deployment.

On the recovery Mac with Python 3, Tailscale, and the existing `sago-cloud` SSH
alias/key, run:

```bash
python3 scripts/private-backups.py pull --force
python3 scripts/private-backups.py install-mac
```

The LaunchAgent `dev.hsichen.sago-cloud-private-backups` checks hourly while the
Mac is awake and logged in, copying once per 24 hours after a successful transfer.
Failures retry on the next check. Network access uses the existing verified SSH
host key and requires noninteractive sudo for the export on Oracle. It briefly
selects the saved `sago-cream.github` Tailscale profile, clears that profile's exit
node, then restores the original profile and connected/disconnected state after
the copy, including on failure. The NTHUSA NAS exit-node setting is preserved.
If the user switches profiles during the copy, the agent leaves that selection
alone. Do not run another network-profile-changing job at the same time.

The export refuses missing databases or a newest snapshot older than 48 hours.
The Mac verifies the manifest, SHA-256 hashes, SQLite integrity and mail table
allowlist before publishing any transferred files. It never extracts tar paths.
Checks and transfer errors log status only, without database contents or secrets.

## Check health

```bash
ssh sago-cloud systemctl status sago-cloud-media-backup.timer sago-cloud-mail-backup.timer
ssh sago-cloud journalctl -u sago-cloud-mail-backup.service --since yesterday
cat "$HOME/Library/Application Support/SagoCloud/backups/last-success.json"
tail -n 20 "$HOME/Library/Logs/SagoCloud/private-backups.log"
launchctl print "gui/$(id -u)/dev.hsichen.sago-cloud-private-backups"
```

The success file records the last complete, verified off-host copy. A date older
than 48 hours needs attention. Neither this agent nor the hourly Git jobs provide
automated notifications. Restoring a missing Mac agent requires the install step
again; Oracle snapshots continue when the Mac is unavailable.

## Restore

Choose a snapshot before the incident, check `PRAGMA integrity_check`, and stop
the affected service. Preserve the current database and its `-wal`/`-shm` siblings
for rollback; move those siblings out of the restored database path while the
service is stopped. Copy the recovered SQLite file with mode 600 and the service
user's ownership, then restart and verify access.

- Media: restore to `/srv/sago-media/.service/media.sqlite`, owner `10001:10001`.
- Mail: restore to the configured `MINISAGO_MAIL_STORE_PATH` inside the bot-core
  state volume (normally `/app/state/mail/access.sqlite`), preserving its original
  service ownership. Restore the matching `MINISAGO_MAIL_ENCRYPTION_KEY` and OAuth
  client configuration from Bitwarden/Vaultwarden. Core recreates the empty
  invitation/session tables on startup. Verify the intended mailbox connection;
  if the grant was revoked, reconnect it instead of reusing the old grant.

Never place these files, the encryption key, or client secrets in the state Git
repository, worker volumes, or application logs.
