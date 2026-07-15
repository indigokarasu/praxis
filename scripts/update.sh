#!/bin/bash
# Wrapper to update ocas-praxis from its GitHub source.
# Usage: ./update.sh [--help]
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: update.sh"
  echo "  Pulls the latest ocas-praxis from its GitHub source (see SKILL.md 'source' field)."
  echo "  Journals and local data under commons/data/ocas-praxis are preserved."
  echo "  Options:"
  echo "    --help, -h   Show this help and exit."
  exit 0
fi

python3 /root/.hermes/scripts/skill_update.py ocas-praxis
