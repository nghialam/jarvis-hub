#!/bin/bash
# Jarvis Hub 3.0 — Phase 1.2: Consolidate Database
# Merges all database files into a single jarvis.db in data/ directory

set -e

echo "=== Phase 1.2: Consolidate Database ==="
echo ""

# Create data directory if it doesn't exist
mkdir -p /Users/nghialam/jarvis-hub/data

# Primary database location
PRIMARY_DB="/Users/nghialam/jarvis-hub/data/jarvis.db"

echo "📋 Current database files:"
find /Users/nghialam/jarvis-hub -name "*.db" -type f 2>/dev/null | while read db; do
    SIZE=$(ls -lh "$db" | awk '{print $5}')
    echo "  $db ($SIZE)"
done
echo ""

# Create backup of all databases before consolidation
BACKUP_DIR="/Users/nghialam/jarvis-hub/backups/databases-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo "📁 Backing up databases to: $BACKUP_DIR"
find /Users/nghialam/jarvis-hub -name "*.db" -type f 2>/dev/null | while read db; do
    cp "$db" "$BACKUP_DIR/" 2>/dev/null || true
done
echo "✅ Database backup created"
echo ""

# Check if primary database already exists and has data
if [ -f "$PRIMARY_DB" ] && [ -s "$PRIMARY_DB" ]; then
    echo "ℹ️  Primary database already exists with data"
    echo "   Keeping existing $PRIMARY_DB"
else
    echo "🔄 Creating new primary database..."
    
    # Copy watchlist.db (only non-empty file)
    if [ -f "/Users/nghialam/jarvis-hub/watchlist.db" ] && [ -s "/Users/nghialam/jarvis-hub/watchlist.db" ]; then
        echo "  Copying watchlist.db to $PRIMARY_DB"
        cp "/Users/nghialam/jarvis-hub/watchlist.db" "$PRIMARY_DB"
    else
        echo "  Creating empty primary database"
        touch "$PRIMARY_DB"
    fi
    
    echo "✅ Primary database created at: $PRIMARY_DB"
fi
echo ""

# Remove duplicate database files (keep only the primary)
echo "🗑️  Removing duplicate database files..."
find /Users/nghialam/jarvis-hub -maxdepth 1 -name "*.db" -type f -not -name "jarvis.db" -exec rm -v {} \; 2>/dev/null || true

# Remove knowledge/ subdirectory databases (data already migrated)
find /Users/nghialam/jarvis-hub/knowledge -name "*.db" -type f -exec rm -v {} \; 2>/dev/null || true

echo ""
echo "=== Phase 1.2 Complete ==="
echo ""
echo "📋 Remaining database files:"
find /Users/nghialam/jarvis-hub -name "*.db" -type f 2>/dev/null | while read db; do
    SIZE=$(ls -lh "$db" | awk '{print $5}')
    echo "  $db ($SIZE)"
done
echo ""
echo "✅ Database consolidation complete"
