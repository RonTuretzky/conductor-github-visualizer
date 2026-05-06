#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect mime.types location
if [ -f /opt/homebrew/etc/nginx/mime.types ]; then
    MIME_TYPES_PATH="/opt/homebrew/etc/nginx/mime.types"
elif [ -f /usr/local/etc/nginx/mime.types ]; then
    MIME_TYPES_PATH="/usr/local/etc/nginx/mime.types"
elif [ -f /etc/nginx/mime.types ]; then
    MIME_TYPES_PATH="/etc/nginx/mime.types"
else
    echo "Error: Could not find nginx mime.types. Install nginx or set MIME_TYPES_PATH manually."
    exit 1
fi

# Generate self-signed cert if missing
if [ ! -f "$SCRIPT_DIR/cert.pem" ] || [ ! -f "$SCRIPT_DIR/key.pem" ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -newkey rsa:2048 -keyout "$SCRIPT_DIR/key.pem" \
        -out "$SCRIPT_DIR/cert.pem" -days 365 -nodes \
        -subj "/CN=localhost" 2>/dev/null
    echo "Certificate created at $SCRIPT_DIR/cert.pem"
fi

# Generate nginx.conf from template
sed -e "s|NGINX_DIR|$SCRIPT_DIR|g" \
    -e "s|PROJECT_ROOT|$PROJECT_ROOT|g" \
    -e "s|MIME_TYPES_PATH|$MIME_TYPES_PATH|g" \
    "$SCRIPT_DIR/nginx.conf" > "$SCRIPT_DIR/nginx.generated.conf"

echo "Generated: $SCRIPT_DIR/nginx.generated.conf"
echo ""
echo "Start nginx with:"
echo "  nginx -c $SCRIPT_DIR/nginx.generated.conf"
echo ""
echo "Then open: https://localhost:8443/tracker3d-visionpro.html"
