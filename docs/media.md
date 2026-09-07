# Sago Media deployment

Sago Cloud deploys the product published by
[`sago-cream/sago-media`](https://github.com/sago-cream/sago-media). Product behavior, authentication,
and the Sago Drop client belong to their application repositories.

## What runs here and why

Sago Media is the self-hosted media backend for Sago Drop. It authorizes devices,
accepts bounded image and video uploads, optimizes images, stores media, and
provides public share links and an administration dashboard. Sago Drop normalizes
videos locally before upload; the server validates and stores them without
transcoding. This is not a pull-request attachment service.

The request flow is:

1. Sago Drop authenticates and uploads through the public media domain.
2. Cloudflare Tunnel and Caddy route API requests to the Bun service.
3. The service tracks authentication and usage in SQLite, runs the image's Linux
   media tools, and writes accepted media to the dedicated filesystem.
4. Caddy serves the stored files directly at their public share URLs.

Oracle is the current host, not an application dependency. This container needs
persistent storage for media and SQLite, native processing tools, and direct
uploads up to 95 MB. A Linux server with equivalent storage and networking could
host it. Moving to Vercel would require redesigning uploads to go directly to
object storage, using a hosted database, and adapting the processing pipeline;
it is not a change of deployment destination alone. Vercel Functions currently
limit request bodies to [4.5 MB](https://vercel.com/docs/functions/limitations).

## Runtime boundary

The `sago-media-api` stack pulls the versioned
`ghcr.io/sago-cream/sago-media:v2.0.0` image. Sago Cloud supplies only:

- a dedicated, bounded filesystem at `/srv/sago-media`;
- runtime secrets and GitHub OAuth configuration;
- a private MiniSago endpoint for access-request DMs;
- private container networking and Caddy routes;
- health checks and resource limits;
- systemd schedules that run the image's prune and verify commands.
- daily backups of authentication state retained for 30 days outside the media
  filesystem.

Override `MEDIA_IMAGE` during deployment to select another immutable release.
The VM never builds media application source.

## Provision and deploy

Create the bounded 10 GiB ext4 filesystem once:

```bash
bun run install:media
```

Copy `env/sago-media-api.env.example` to
`/srv/sago-cloud/secrets/sago-media-api.env`, fill in the OAuth and owner values,
then deploy:

```bash
bun run deploy:sago-media-api
bun run deploy:edge
```

Set the same `MEDIA_ACCESS_NOTIFICATION_SECRET` in `sago-media-api.env` and
`bot-core.env`. Keep `MEDIA_ACCESS_NOTIFICATION_URL` on the private
`http://bot-core:3000/api/internal/media-access-request` address.

The deployment starts the maintenance timers only after the service health
check succeeds. Static content is served directly by Caddy with immutable cache
headers; API, login, activation, and admin routes are proxied without caching.

## Operations

```bash
bun run status
ssh sago-cloud systemctl status sago-cloud-media-prune.timer
ssh sago-cloud systemctl status sago-cloud-media-verify.timer
ssh sago-cloud systemctl status sago-cloud-media-backup.timer
```

The timers execute `sago-media-prune` and `sago-media-verify` inside the running
product container. Their implementation and retention policy therefore remain
versioned with the product image, while Sago Cloud owns when and where they run.
The backup timer serializes and verifies `.service/media.sqlite` into
`/srv/sago-cloud/backups/sago-media`.

## Release and upgrade

The deployment is `sago-media-api`, product commands are `sago-media-*`, and
configuration uses `MEDIA_*`. The image is pinned to version 2.0.0, which must be
published by Sago Media before this infrastructure change is deployed.

Existing installations must follow [the 2.0 migration](media-migration.md).
The migration moves the existing filesystem and SQLite state, renames secrets
and scheduled jobs, and replaces the old Compose project. It includes a
maintenance window and rollback procedure. There are no runtime aliases for the
old names. Public hostnames, HTTP endpoints, and media hashes remain unchanged.
