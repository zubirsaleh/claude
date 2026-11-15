#!/usr/bin/env bash
# Create local development secrets (gitignored). Never reuse these in production.
# Files are group-owned by GID 10001 (the API container's group) with mode 0640, because
# Compose file secrets are bind mounts that keep host ownership and permissions.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p secrets
chmod 700 secrets
umask 077
[ -s secrets/db_password ] || openssl rand -hex 24 > secrets/db_password
[ -s secrets/operator_token ] || openssl rand -hex 32 > secrets/operator_token
chgrp 10001 secrets/db_password secrets/operator_token 2>/dev/null \
  || sudo chgrp 10001 secrets/db_password secrets/operator_token
chmod 640 secrets/db_password secrets/operator_token
echo "secrets/ ready (db_password, operator_token)"
