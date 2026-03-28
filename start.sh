#!/bin/bash
# Klaviertrainer – Setup & Start Script
# Run once to set up, then use to start the server

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Klaviertrainer Setup ==="

# Create virtualenv if missing
if [ ! -d "venv" ]; then
  echo "→ Creating Python virtualenv..."
  python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "→ Installing dependencies..."
pip install -q -r requirements.txt

# Create uploads directory
mkdir -p uploads

# Generate a persistent secret key if not set
if [ ! -f ".secret_key" ]; then
  python3 -c "import secrets; print(secrets.token_hex(32))" > .secret_key
  echo "→ Generated new secret key"
fi

export SECRET_KEY=$(cat .secret_key)

# Port: default 8080 (5000 is taken by AirPlay on Mac)
PORT="${PORT:-8080}"

# Init DB
echo "→ Initialising database..."
python3 -c "from app import init_db; init_db(); print('DB ready.')"

echo ""
echo "=== Starting server ==="
echo "→ Running on http://localhost:${PORT}"
echo "   Press Ctrl+C to stop"
echo ""

# Production: gunicorn with 4 workers
# For dev/small server: use Flask directly with FLASK_DEBUG=1 ./start.sh
if [ "${FLASK_DEBUG}" = "1" ]; then
  python3 app.py
else
  gunicorn \
    --workers 4 \
    --bind "0.0.0.0:${PORT}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "app:app"
fi
