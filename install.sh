#!/bin/bash
set -e

# ─────────────────────────────────────────────────────────────────────────────
#  QuickPalm Analyser — One-Command Installer
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "  ██████╗ ██████╗ ███████╗██████╗ ██╗ ██████╗████████╗ ██████╗ ██████╗ ███████╗"
echo "  ██╔══██╗██╔══██╗██╔════╝██╔══██╗██║██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██╔════╝"
echo "  ██████╔╝██████╔╝█████╗  ██║  ██║██║██║        ██║   ██║   ██║██████╔╝███████╗"
echo "  ██╔═══╝ ██╔══██╗██╔══╝  ██║  ██║██║██║        ██║   ██║   ██║██╔═══╝ ╚════██║"
echo "  ██║     ██║  ██║███████╗██████╔╝██║╚██████╗   ██║   ╚██████╔╝██║     ███████║"
echo "  ╚═╝     ╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝     ╚══════╝"
echo ""
echo "  Server Intelligence Platform — Installer"
echo ""

# ── Check prerequisites ───────────────────────────────────────────────────────

info "Checking prerequisites..."

command -v docker >/dev/null 2>&1 || error "Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"

if ! docker compose version >/dev/null 2>&1; then
  info "Installing Docker Compose Plugin..."
  mkdir -p ~/.docker/cli-plugins
  curl -SL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" \
    -o ~/.docker/cli-plugins/docker-compose
  chmod +x ~/.docker/cli-plugins/docker-compose
fi

success "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
success "Docker Compose $(docker compose version --short)"

# ── Provision .env ────────────────────────────────────────────────────────────

if [ ! -f .env ]; then
  info "No .env found — creating one from .env.example..."
  cp .env.example .env
  GENERATED_PASSWORD=$(openssl rand -hex 12)
  sed -i "s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=${GENERATED_PASSWORD}/" .env
  success "Generated Grafana admin password (shown below, also saved in .env)"
  warn "Grafana login: admin / ${GENERATED_PASSWORD}"
else
  success ".env already present — using existing configuration"
fi

# ── Check ports ──────────────────────────────────────────────────────────────

info "Checking ports..."
for port in 80 3000 8000 8001 8080 9090; do
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    warn "Port $port is already in use — may cause conflicts"
  fi
done

# ── Start services ────────────────────────────────────────────────────────────

info "Building Docker images (first run: ~3-5 minutes)..."
docker compose build

info "Starting all services..."
docker compose up -d

# ── Wait for services to be ready ─────────────────────────────────────────────

info "Waiting for services to be ready..."

wait_for() {
  local name=$1
  local url=$2
  local max=30
  local count=0
  printf "  Waiting for %-20s" "$name..."
  until curl -sf "$url" >/dev/null 2>&1; do
    sleep 2
    count=$((count + 1))
    if [ $count -ge $max ]; then
      echo " TIMEOUT"
      return 1
    fi
    printf "."
  done
  echo " ready"
}

wait_for "Collector"   "http://localhost:8000/metrics"
wait_for "Prometheus"  "http://localhost:9090/-/healthy"
wait_for "Grafana"     "http://localhost:3000/api/health"
wait_for "ML Service"  "http://localhost:8001/metrics"
wait_for "Chat"        "http://localhost:8080/status"
wait_for "Nginx"       "http://localhost"

# ── Check Ollama model ────────────────────────────────────────────────────────

OLLAMA_MODEL=${OLLAMA_MODEL:-"llama3.2:1b"}

if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  if ! curl -sf http://localhost:11434/api/tags | grep -q "$OLLAMA_MODEL"; then
    info "Loading LLM model ($OLLAMA_MODEL)..."
    ollama pull "$OLLAMA_MODEL" || warn "Model could not be loaded. Run manually: ollama pull $OLLAMA_MODEL"
  else
    success "LLM model $OLLAMA_MODEL available"
  fi
else
  warn "Ollama not found. Chat will work without LLM responses."
  warn "Install Ollama: https://ollama.ai"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║         QuickPalm Analyser is running!                        ║"
echo "  ║                                                  ║"
echo "  ║  Chat Interface:  http://localhost               ║"
echo "  ║  Grafana:         http://localhost/grafana       ║"
echo "  ║                   Login: admin / <see .env>      ║"
echo "  ║  Prometheus:      http://localhost:9090          ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

success "Installation complete!"
