#!/usr/bin/env bash
set -euo pipefail

# Heurística simples para bloquear segredos comuns.
if rg -n --hidden --glob '!.git' '(AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|secret[_-]?key\s*=|api[_-]?key\s*=|password\s*=)' .; then
  echo "Potential secrets detected."
  exit 1
fi

echo "No obvious secrets detected."
