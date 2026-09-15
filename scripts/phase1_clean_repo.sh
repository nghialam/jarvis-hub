#!/bin/bash
# Jarvis Hub 3.0 — Phase 1.1: Clean Repository
# Removes all backup files, fix scripts, duplicate code, and dead code

set -e

echo "=== Phase 1.1: Clean Repository ==="
echo "Working directory: $(pwd)"
echo ""

# Count files before cleanup
BEFORE_COUNT=$(find . -maxdepth 1 -type f \( -name "*.bak*" -o -name "fix_*" -o -name "app.py.rebuild*" -o -name "app.py.patch" -o -name "jarvis_app*" -o -name "hotfix_*" -o -name "flask_dashboard*" -o -name "app_append*" -o -name "app_signals*" -o -name "app_tail*" -o -name "_fix*" -o -name "_survey*" -o -name "gotham_brief*" -o -name "market.py.bak*" -o -name "news.py.bak*" -o -name "index.html.bak*" \) 2>/dev/null | wc -l | tr -d ' ')

echo "📊 Files to remove: ${BEFORE_COUNT}"
echo ""

# List files to be removed
echo "📁 Files to be removed:"
find . -maxdepth 1 -type f \( -name "*.bak*" -o -name "fix_*" -o -name "app.py.rebuild*" -o -name "app.py.patch" -o -name "jarvis_app*" -o -name "hotfix_*" -o -name "flask_dashboard*" -o -name "app_append*" -o -name "app_signals*" -o -name "app_tail*" -o -name "_fix*" -o -name "_survey*" -o -name "gotham_brief*" -o -name "market.py.bak*" -o -name "news.py.bak*" -o -name "index.html.bak*" \) 2>/dev/null | sort

echo ""
echo "🗑️  Removing files..."

# Remove all backup files (app.py.bak*, app.py.backup*, etc.)
find . -maxdepth 1 -type f -name "app.py.bak*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app.py.backup*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app.py.rebuild*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app.py.patch" -exec rm -v {} \; 2>/dev/null || true

# Remove all fix scripts
find . -maxdepth 1 -type f -name "fix_*" -exec rm -v {} \; 2>/dev/null || true

# Remove duplicate db.py in root (keep core/db.py)
if [ -f "db.py" ]; then
    echo "Removing duplicate db.py (keeping core/db.py)"
    rm -v db.py
fi

# Remove database.py.bak files
find . -maxdepth 1 -type f -name "*.bak*" -exec rm -v {} \; 2>/dev/null || true

# Remove legacy gotham_brief files
find . -maxdepth 1 -type f -name "gotham_brief*" -exec rm -v {} \; 2>/dev/null || true

# Remove hotfix files
find . -maxdepth 1 -type f -name "hotfix_*" -exec rm -v {} \; 2>/dev/null || true

# Remove other temp/dead files
find . -maxdepth 1 -type f -name "jarvis_app*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "flask_dashboard*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app_append*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app_signals*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "app_tail*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "_fix*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "_survey*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "market.py.bak*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "news.py.bak*" -exec rm -v {} \; 2>/dev/null || true
find . -maxdepth 1 -type f -name "index.html.bak*" -exec rm -v {} \; 2>/dev/null || true

echo ""
echo "=== Phase 1.1 Complete ==="

# Count files after cleanup
AFTER_COUNT=$(find . -maxdepth 1 -type f \( -name "*.bak*" -o -name "fix_*" -o -name "app.py.rebuild*" -o -name "app.py.patch" -o -name "jarvis_app*" -o -name "hotfix_*" -o -name "flask_dashboard*" -o -name "app_append*" -o -name "app_signals*" -o -name "app_tail*" -o -name "_fix*" -o -name "_survey*" -o -name "gotham_brief*" -o -name "market.py.bak*" -o -name "news.py.bak*" -o -name "index.html.bak*" \) 2>/dev/null | wc -l | tr -d ' ')

echo "📊 Files before: ${BEFORE_COUNT}"
echo "📊 Files after: ${AFTER_COUNT}"
echo "📊 Files removed: $((BEFORE_COUNT - AFTER_COUNT))"
echo ""
echo "✅ Repository cleaned successfully"
