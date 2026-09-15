#!/usr/bin/env bash
# Jarvis Hub 3.0 - Bootstrap Install Script (Phase 1.5)
# Usage: bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "============================================================"
echo "  Jarvis Hub 3.0 - Bootstrap Installer"
echo "============================================================"
echo ""

# --- Step 1: Check Python version ---
log_info "Checking Python version..."
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    log_error "Python not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
log_ok "Python found: $PYTHON_VERSION"

# --- Step 2: Create virtual environment ---
log_info "Creating virtual environment..."
VENV_DIR="$SCRIPT_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    log_warn "Virtual environment already exists at $VENV_DIR"
    log_info "Reusing existing venv..."
else
    $PYTHON_CMD -m venv "$VENV_DIR"
    log_ok "Virtual environment created at $VENV_DIR"
fi

# --- Step 3: Activate venv ---
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    log_error "Virtual environment activation script not found at $ACTIVATE_SCRIPT"
    exit 1
fi

source "$ACTIVATE_SCRIPT"
log_ok "Virtual environment activated"

# --- Step 4: Upgrade pip ---
log_info "Upgrading pip..."
pip install --upgrade pip setuptools wheel >/dev/null 2>&1
log_ok "pip upgraded"

# --- Step 5: Install requirements ---
log_info "Installing Python dependencies from requirements.txt..."
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    pip install -r "$SCRIPT_DIR/requirements.txt"
    log_ok "Dependencies installed"
else
    log_error "requirements.txt not found at $SCRIPT_DIR/requirements.txt"
    exit 1
fi

# --- Step 6: Create directories ---
log_info "Creating required directories..."
mkdir -p "$SCRIPT_DIR/data"
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/backups"
mkdir -p "$SCRIPT_DIR/cache"
log_ok "Directories created"

# --- Step 7: Initialize database ---
log_info "Initializing database..."
INIT_DB_SCRIPT="$SCRIPT_DIR/scripts/init_db.py"
if [ -f "$INIT_DB_SCRIPT" ]; then
    $PYTHON_CMD "$INIT_DB_SCRIPT"
    log_ok "Database initialized"
else
    log_warn "No init_db.py found — database will be created on first run"
    log_info "Running database migration via app..."
    # Create empty jarvis.db with basic tables
    DB_FILE="$SCRIPT_DIR/data/jarvis.db"
    if [ ! -f "$DB_FILE" ] || [ ! -s "$DB_FILE" ]; then
        # Create a minimal DB
        $PYTHON_CMD -c "
import sqlite3, os
db_path = '$DB_FILE'
os.makedirs(os.path.dirname(db_path), exist_ok=True)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
# Create minimal tables needed for the app to start
cursor.execute('''CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    collected_data TEXT,
    section_1 TEXT, section_2 TEXT, section_3 TEXT, section_4 TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    name TEXT,
    price REAL, change_pct REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()
conn.close()
print('Database created at ' + db_path)
"
        log_ok "Database initialized at $DB_FILE"
    fi
fi

# --- Step 8: Verify installation ---
log_info "Verifying installation..."
VERIFY_ERRORS=0

# Check critical modules
for module in flask requests pyyaml; do
    if $PYTHON_CMD -c "import $module" 2>/dev/null; then
        log_ok "$module installed"
    else
        log_error "$module not installed"
        VERIFY_ERRORS=$((VERIFY_ERRORS + 1))
    fi
done

# Check database
if [ -f "$DB_FILE" ] && [ -s "$DB_FILE" ]; then
    log_ok "Database exists at $DB_FILE"
else
    log_warn "Database file missing or empty at $DB_FILE"
fi

# --- Step 9: Summary ---
echo ""
echo "============================================================"
if [ $VERIFY_ERRORS -eq 0 ]; then
    log_ok "Installation completed successfully!"
    echo ""
    echo "  Next steps:"
    echo "    1. Configure: Edit $SCRIPT_DIR/config.yaml"
    echo "    2. Run:       $PYTHON_CMD app.py"
    echo "    3. Access:    http://localhost:8100/hub2"
    echo ""
else
    log_error "$VERIFY_ERRORS verification error(s) detected"
    echo ""
    echo "  Please check the errors above and try again."
fi
echo "============================================================"
echo ""

# Keep venv activated for user
# (In production, user should run: source .venv/bin/activate)
