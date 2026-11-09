#!/bin/bash
# Creates a self-signed certificate so browsers on the local network will allow the microphone.
# Usage: scripts/make_cert.sh <server-ip>
cd "$(dirname "$0")/.." || exit 1
[ -n "$1" ] || { echo "Usage: scripts/make_cert.sh <server-ip>"; exit 1; }
mkdir -p certs
timeout 60 openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=shahrazad" -addext "subjectAltName=IP:$1" -keyout certs/key.pem -out certs/cert.pem 2>/dev/null || exit 1
chmod 600 certs/key.pem
echo "Created certs/cert.pem for $1. In .env set TUTOR_HOST=$1, TUTOR_SSL_CERT=certs/cert.pem and TUTOR_SSL_KEY=certs/key.pem"
