export const routes = [
  {
    hostname: "<homepage-hostname>",
    tunnelProtocol: "https",
    caddy: `{$HOMEPAGE_DOMAIN} {
\tencode zstd gzip
\tlog

\theader {
\t\tReferrer-Policy no-referrer
\t\tX-Content-Type-Options nosniff
\t}

\treverse_proxy homepage:3102
}`,
  },
  {
    hostname: "<obi-hostname>",
    tunnelProtocol: "https",
    caddy: `{$OBI_DOMAIN} {
\tencode zstd gzip
\tlog

\theader {
\t\tReferrer-Policy no-referrer
\t\tX-Content-Type-Options nosniff
\t\tX-Frame-Options DENY
\t\t-Server
\t}

\treverse_proxy obi:5984 {
\t\tflush_interval -1
\t}
}`,
  },
  {
    hostname: "<bot-hostname>",
    tunnelProtocol: "https",
    caddy: `{$DOMAIN} {
\tencode zstd gzip
\tlog

\theader {
\t\tReferrer-Policy no-referrer
\t\tX-Content-Type-Options nosniff
\t}

\tredir /bot /bot/ 308

\thandle_path /bot/* {
\t\treverse_proxy bot-core:3000
\t}

\thandle {
\t\treverse_proxy bot-core:3000
\t}
}`,
  },
  {
    hostname: "<no5-hostname>",
    tunnelProtocol: "http",
    caddy: `http://{$NO5_DOMAIN} {
\tencode zstd gzip
\tlog

\theader {
\t\tCache-Control "private, no-store"
\t\tReferrer-Policy no-referrer
\t\tX-Content-Type-Options nosniff
\t\tX-Frame-Options DENY
\t\t-Server
\t}

\t@allowed client_ip {$NO5_ALLOWED_IP}

\thandle @allowed {
\t\troot * /srv/no-5
\t\ttry_files {path} /index.html
\t\tfile_server
\t}

\thandle {
\t\theader Content-Type "text/plain; charset=utf-8"
\t\trespond "This private site is only available from the No.5 home network." 403
\t}
}`,
  },
  {
    hostname: "<media-hostname>",
    tunnelProtocol: "http",
    caddy: `http://{$MEDIA_DOMAIN} {
\tlog

\theader {
\t\tReferrer-Policy no-referrer
\t\tX-Content-Type-Options nosniff
\t\t-Server
\t}

\t@media_api path /v1/* /activate /auth/* /admin /admin/*

\thandle @media_api {
\t\trequest_body {
\t\t\tmax_size 95000000
\t\t}

\t\theader {
\t\t\tCache-Control no-store
\t\t}

\t\treverse_proxy pr-media-api:3000
\t}

\t@supported_media path_regexp supported_media ^/[0-9a-f]{2}/[0-9a-f]{64}\\.(?:gif|jpeg|jpg|mp4|png|webm|webp)$

\thandle @supported_media {
\t\theader {
\t\t\tAccess-Control-Allow-Origin *
\t\t\tCache-Control "public, max-age=31536000, s-maxage=31536000, immutable"
\t\t\tCross-Origin-Resource-Policy cross-origin
\t\t}

\t\troot * /srv/pr-media
\t\tfile_server
\t}

\trespond 404
}`,
  },
];
