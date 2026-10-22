FROM golang:1.27.3-alpine AS builder

RUN apk add --no-cache --upgrade ca-certificates git
RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@v0.4.7
RUN xcaddy build v2.11.4 --output /usr/bin/caddy

FROM caddy:2.11.4-alpine

RUN apk add --no-cache --upgrade ca-certificates
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
