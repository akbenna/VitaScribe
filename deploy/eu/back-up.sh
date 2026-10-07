#!/bin/sh
# Nachtelijke back-up van het register (praktijken, gebruikers, geleerde regels, auditlog).
# Er staan geen opnames of verslagen in de database. Crontab: 15 2 * * * /pad/naar/deploy/eu/back-up.sh
set -e
cd "$(dirname "$0")"
docker compose exec -T postgres pg_dump -U vitascribe -Fc vitascribe > "back-ups/register-$(date +%F).dump"
# Bewaar 30 dagen.
find back-ups -name 'register-*.dump' -mtime +30 -delete
