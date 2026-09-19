#!/bin/bash
# JH3.0 SSL/HTTPS Setup with Let's Encrypt (Certbot)
# Deploy on: Linux server (not macOS — use http for local)
# Prerequisite: JH3.0 deployed, nginx configured (P5.10), domain pointing to server
#
# Usage: sudo bash deploy/ssl-letsencrypt.sh
set -euo pipefail

DOMAIN="${1:-jarvis.example.com}"
EMAIL="${2:-admin@example.com}"
NGINX_CONF="/etc/nginx/sites-available/jarvis-hub.conf"

echo "=== JH3.0 SSL Setup (Let's Encrypt) ==="
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"

# 1. Verify DNS resolves
echo "[1/5] Checking DNS resolution..."
if ! dig +short "$DOMAIN" > /dev/null 2>&1; then
    echo "WARNING: DNS may not be ready. certbot can still run but may fail."
fi

# 2. Install certbot (if not present)
echo "[2/5] Installing certbot..."
if ! command -v certbot &> /dev/null; then
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx
    elif command -v yum &> /dev/null; then
        sudo yum install -y certbot python3-certbot-nginx
    elif command -v brew &> /dev/null; then
        brew install certbot
    else
        echo "ERROR: Could not install certbot. Install manually."
        exit 1
    fi
fi

# 3. Stop nginx temporarily (for standalone mode) or use nginx plugin
echo "[3/5] Obtaining SSL certificate..."
if command -v apt-get &> /dev/null || command -v yum &> /dev/null; then
    # Use nginx plugin (auto-configures nginx)
    sudo certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --redirect --non-interactive
else
    # macOS or other — use standalone mode
    # First, ensure port 80 is free
    echo "NOTE: Running in standalone mode. nginx must be stopped."
    sudo certbot certonly -d "$DOMAIN" --email "$EMAIL" --agree-tos --redirect --non-interactive --standalone
fi

echo "Certificate obtained. Paths:"
echo "  Full chain: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
echo "  Private:    /etc/letsencrypt/live/$DOMAIN/privkey.pem"

# 4. Update nginx config if using standalone mode
echo "[4/5] Configuring nginx for HTTPS..."
if [ ! -f "$NGINX_CONF" ]; then
    # nginx plugin already handled this; create minimal config
    cat > "$NGINX_CONF" <<EOF
server {
    listen 443 ssl;
    server_name $DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}
EOF
    echo "Created $NGINX_CONF"
fi

# 5. Test and reload nginx
echo "[5/5] Testing and reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx
echo "✅ SSL setup complete!"
echo ""
echo "Auto-renewal:"
echo "  certbot renew --dry-run  (test renewal)"
echo "  systemctl list-timers | grep certbot  (check cron)"

# Configure renewal if not present
if ! systemctl list-timers 2>/dev/null | grep -q certbot; then
    echo ""
    echo "NOTE: certbot auto-renewal not detected. Set up manually:"
    echo "  sudo systemctl enable certbot.timer"
fi
