#!/bin/bash
# Wird beim ersten EC2-Start ausgeführt
set -e

apt-get update -y
apt-get install -y docker.io git curl

# Docker Compose Plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Docker starten
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Projekt klonen (wird von Ansible später befüllt)
mkdir -p /opt/predictops
