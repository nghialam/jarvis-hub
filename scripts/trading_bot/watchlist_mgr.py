#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Watchlist Manager
Quản lý danh mục theo dõi (CRUD, lưu JSON, chuẩn hóa symbol).
"""

import json
import os
import re
from datetime import datetime

try:
    from config import WATCHLIST_FILE, MAX_STOCKS_IN_WATCHLIST
except ImportError:
    WATCHLIST_FILE = "/Users/nghialam/jarvis-hub/scripts/trading_bot/watchlist.json"
    MAX_STOCKS_IN_WATCHLIST = 30

# ═══════════════════╗
# Symbol Validation - VN stocks: uppercase letters only, 2-6 chars
# ╔╝
VN_SYMBOL_PATTERN = re.compile(r'^[A-Z]{1,6}$')


def validate_symbol(symbol: str) -> bool:
    """Kiểm tra symbol hợp lệ."""
    sym = symbol.upper().strip()
    if not VN_SYMBOL_PATTERN.match(sym):
        return False
    # Các symbol đặc biệt không hỗ trợ
    blocked = ['HOT', 'UPC', 'CAPT', 'DAG']  # sample blocking list
    return sym not in blocked


def load_watchlist(path: str = WATCHLIST_FILE) -> dict:
    """
    Load watchlist từ file JSON.
    Structure: {
        "stocks": ["VCI", "VIC", "VCB", ...],
        "updated_at": "2026-05-26T13:00:00",
        "settings": {
            "auto_halt_minutes": 30,  # Pause after too many signals
            "max_signals_per_day": 20
        }
    }
    """
    if not os.path.exists(path):
         # Create default
         data = {
             "stocks": [],
             "updated_at": datetime.now().isoformat(),
             "settings": {
                 "auto_halt_minutes": 30,
                 "max_signals_per_day": 20
             }
         }
         save_watchlist(data, path)
         return data

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
          # Validate structure
        if "stocks" not in data:
            data["stocks"] = []
        if "settings" not in data:
            data["settings"] = {
                "auto_halt_minutes": 30,
                "max_signals_per_day": 20
            }
        
         # Normalize symbols
        data["stocks"] = [s.upper().strip() for s in data["stocks"]]
        return data
    
    except (json.JSONDecodeError, IOError) as e:
        print(f"[WARN] Could not read watchlist: {e}. Creating default.")
        data = {
            "stocks": [],
            "updated_at": datetime.now().isoformat(),
            "settings": {"auto_halt_minutes": 30, "max_signals_per_day": 20}
        }
        save_watchlist(data, path)
        return data


def add_stock(symbol: str, path: str = WATCHLIST_FILE) -> bool:
    """Thêm một mã vào watchlist."""
    sym = symbol.upper().strip()
    
    if not validate_symbol(sym):
        print(f"[ERROR] Symbol không hợp lệ: {symbol}. Chỉ cho phép chữ hoa 1-6 ký tự.")
        return False
    
    data = load_watchlist(path)
    
    if sym in data["stocks"]:
        print(f"[INFO] {sym} đã có trong watchlist.")
        return False
    
    if len(data["stocks"]) >= MAX_STOCKS_IN_WATCHLIST:
        print(f"[ERROR] Watchlist đầy ({MAX_STOCKS_IN_WATCHLIST} mã).")
        return False
    
    data["stocks"].append(sym)
    data["updated_at"] = datetime.now().isoformat()
    save_watchlist(data, path)
    print(f"[OK] Đã thêm {sym} vào watchlist.")
    return True


def remove_stock(symbol: str, path: str = WATCHLIST_FILE) -> bool:
    """Xóa một mã khỏi watchlist."""
    sym = symbol.upper().strip()
    
    data = load_watchlist(path)
    
    if sym not in data["stocks"]:
        print(f"[INFO] {sym} không có trong watchlist.")
        return False
    
    data["stocks"].remove(sym)
    data["updated_at"] = datetime.now().isoformat()
    save_watchlist(data, path)
    print(f"[OK] Đã xóa {sym} khỏi watchlist.")
    return True


def list_stocks(path: str = WATCHLIST_FILE) -> str:
    """Trả về danh sách dạng text đẹp."""
    data = load_watchlist(path)
    stocks = data["stocks"]
    
    if not stocks:
        return "⚠️ Watchlist trống. Dùng 'add <SYMBOL>' để thêm mã."
    
    lines = ["📋 Danh sách theo dõi:", f"   Tổng cộng: {len(stocks)} mã", ""]
    for i, sym in enumerate(stocks, 1):
        lines.append(f"   {i}. {sym}")
    return "\n".join(lines)


def save_watchlist(data: dict, path: str = WATCHLIST_FILE) -> None:
    """Lưu watchlist vào file JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_watchlist(path: str = WATCHLIST_FILE) -> None:
    """Xóa toàn bộ watchlist."""
    save_watchlist({
        "stocks": [],
        "updated_at": datetime.now().isoformat(),
        "settings": {"auto_halt_minutes": 30, "max_signals_per_day": 20}
    }, path)
    print("[OK] Watchlist đã được xóa sạch.")


if __name__ == "__main__":
      # Test basic operations
     data = load_watchlist()
     print(list_stocks())
