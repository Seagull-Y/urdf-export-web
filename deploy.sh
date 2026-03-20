#!/usr/bin/env bash
# deploy.sh — one-click deploy for URDF Exporter web service
set -euo pipefail

echo "╔══════════════════════════════════════════╗"
echo "║    URDF Exporter — One-Click Deploy      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Prerequisite checks ─────────────────────────────────────────
command -v docker &>/dev/null || { echo "❌  docker not found — install Docker first."; exit 1; }

if command -v docker-compose &>/dev/null; then
  DC="docker-compose"
elif docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
else
  echo "❌  Docker Compose not found (neither 'docker-compose' nor 'docker compose')."
  exit 1
fi

echo "✓  Docker: $(docker --version)"
echo "✓  Compose: $($DC version 2>/dev/null | head -1)"
echo ""

# ── .env setup ──────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝  Created .env from template."
  echo "    Edit it with your Onshape API credentials:"
  echo ""
  echo "      nano .env"
  echo ""
  echo "    Or leave blank — you can enter credentials per-export in the web UI."
  echo "    Re-run this script when ready."
  echo ""
  exit 0
fi

if grep -q "your_access_key_here" .env 2>/dev/null; then
  echo "⚠️   .env still has placeholder credentials."
  echo "    Users can enter credentials manually in the UI."
  echo ""
fi

# ── Create runtime dirs ─────────────────────────────────────────
mkdir -p jobs static

# ── Build & start ───────────────────────────────────────────────
echo "🔨  Building Docker image…"
$DC build --pull

echo ""
echo "🚀  Starting service…"
$DC up -d

echo ""
echo "⏳  Waiting for health check…"
for i in $(seq 1 15); do
  if curl -sf http://localhost:8000/api/jobs &>/dev/null; then
    echo "✓  Service is up!"
    break
  fi
  sleep 2
done

# ── Print access info ───────────────────────────────────────────
echo ""
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "═══════════════════════════════════════════"
echo "  Access the web UI at:"
echo "    Local  → http://localhost:8000"
echo "    LAN    → http://${SERVER_IP}:8000"
echo ""
echo "  Useful commands:"
echo "    $DC logs -f        # tail logs"
echo "    $DC down           # stop"
echo "    $DC restart        # restart"
echo "    $DC pull && $DC up -d  # update"
echo "═══════════════════════════════════════════"
