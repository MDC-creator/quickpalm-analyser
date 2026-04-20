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

# ── Voraussetzungen prüfen ────────────────────────────────────────────────────

info "Prüfe Voraussetzungen..."

command -v docker >/dev/null 2>&1 || error "Docker ist nicht installiert. Bitte zuerst Docker installieren: https://docs.docker.com/get-docker/"

if ! docker compose version >/dev/null 2>&1; then
  info "Docker Compose Plugin installieren..."
  mkdir -p ~/.docker/cli-plugins
  curl -SL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" \
    -o ~/.docker/cli-plugins/docker-compose
  chmod +x ~/.docker/cli-plugins/docker-compose
fi

success "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
success "Docker Compose $(docker compose version --short)"

# ── Ports prüfen ─────────────────────────────────────────────────────────────

info "Prüfe Ports..."
for port in 80 3000 8000 8001 8080 9090; do
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    warn "Port $port ist bereits belegt — könnte Konflikte geben"
  fi
done

# ── Services starten ──────────────────────────────────────────────────────────

info "Baue Docker Images (erste Ausführung: ~3-5 Minuten)..."
docker compose build

info "Starte alle Services..."
docker compose up -d

# ── Warten bis alles bereit ist ───────────────────────────────────────────────

info "Warte bis Services bereit sind..."

wait_for() {
  local name=$1
  local url=$2
  local max=30
  local count=0
  printf "  Warte auf %-20s" "$name..."
  until curl -sf "$url" >/dev/null 2>&1; do
    sleep 2
    count=$((count + 1))
    if [ $count -ge $max ]; then
      echo " TIMEOUT"
      return 1
    fi
    printf "."
  done
  echo " bereit"
}

wait_for "Collector"   "http://localhost:8000/metrics"
wait_for "Prometheus"  "http://localhost:9090/-/healthy"
wait_for "Grafana"     "http://localhost:3000/api/health"
wait_for "ML Service"  "http://localhost:8001/metrics"
wait_for "Chat"        "http://localhost:8080/status"
wait_for "Nginx"       "http://localhost"

# ── Ollama Modell prüfen ──────────────────────────────────────────────────────

OLLAMA_MODEL=${OLLAMA_MODEL:-"llama3.2:1b"}

if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  if ! curl -sf http://localhost:11434/api/tags | grep -q "$OLLAMA_MODEL"; then
    info "Lade LLM Modell ($OLLAMA_MODEL)..."
    ollama pull "$OLLAMA_MODEL" || warn "Modell konnte nicht geladen werden. Manuell: ollama pull $OLLAMA_MODEL"
  else
    success "LLM Modell $OLLAMA_MODEL verfügbar"
  fi
else
  warn "Ollama nicht gefunden. Chat funktioniert ohne LLM-Antworten."
  warn "Installiere Ollama: https://ollama.ai"
fi

# ── Fertig ────────────────────────────────────────────────────────────────────

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║         QuickPalm Analyser is running!                        ║"
echo "  ║                                                  ║"
echo "  ║  Chat Interface:  http://localhost               ║"
echo "  ║  Grafana:         http://localhost/grafana       ║"
echo "  ║                   Login: admin / quickpalm       ║"
echo "  ║  Prometheus:      http://localhost:9090          ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

success "Installation abgeschlossen!"
