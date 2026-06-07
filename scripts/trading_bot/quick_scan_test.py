#!/usr/bin/env python3
"""Quick scan test - verify all indicators after the fix."""
import sys, warnings, time
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/nghialam/jarvis-hub/scripts/trading_bot')

from signal_engine import SignalEngine as SE
from market_data import fetch_stock_data

engine = SE()
all_symbols = ['VCI','VIC','VCB','DGW','FTS','TCB','HCM','PDR',
                'NLG','DXG','BMP','VGI','FRT','VIX','CTD','MBB','FPT','VHM']

results = {}

# Scan symbols
for sym in all_symbols:
    d = fetch_stock_data(sym)
    s = engine.analyze_stock(d)
    
    price = d.get('latest_price')
    rsi = d.get('rsi_14')
    macd_v = d.get('macd_line', 0) or 0
    hist = d.get('histogram', 0) or 0
    ma5 = d.get('ma_5')
    ma20 = d.get('ma_20')
    
    signal_val = ''
    conf = 0
    if isinstance(s, dict):
        signal_val = s['signal']
        conf = s.get('confidence', 0) or 0

    results[sym] = {
        'price': price,
        'rsi': rsi,
        'macd': macd_v,
        'histogram': hist,
        'signal': signal_val,
        'confidence': conf,
        'ma5': ma5,
        'ma20': ma20,
    }

    if d.get('status') in ('ok', 'partial'):
        sig_mark = "BUY" if signal_val == "BUY" else ("SELL" if signal_val == "SELL" else "HOLD")
        print(f"{sym}: price={price} rsi={rsi} macd_v={macd_v:+.4f} hist={hist:+.4f} ma5={'%.2f' % ma5 if ma5 else '?'} ma20={'%.2f' % ma20 if ma20 else '?'} | signal={sig_mark} conf={conf}")
    time.sleep(2)

print("\n==== INDICATOR ANALYSIS ====")
rsi_list = [(sym, r['rsi']) for sym, r in results.items() 
             if isinstance(r.get('rsi'), (int, float))]
for sym, rsi in sorted(rsi_list, key=lambda x: x[1]):
    emoji = "RED" if rsi > 68 else ("GREEN" if rsi < 32 else "WHITE")
    print(f"{sym}: RSI={rsi:.2f} {emoji}")

# Signal breakdown
buy_n = sum(1 for r in results.values() 
            if isinstance(r.get('signal'), str) and r['signal'] == 'BUY')
sell_n = sum(1 for r in results.values() 
             if isinstance(r.get('signal'), str) and r['signal'] == 'SELL')
hold_n = sum(1 for r in results.values() 
             if isinstance(r.get('signal'), str) and r['signal'] == 'HOLD')
print(f"\nBUY={buy_n} | SELL={sell_n} | HOLD={hold_n} | Total={len(results)}")

# RSI ranges
rsi_under_30 = sum(1 for _, v in rsi_list if v < 30)
rsi_40_50 = sum(1 for _, v in rsi_list if 40 <= v < 50)
rsi_50_60 = sum(1 for _, v in rsi_list if 50 <= v < 60)
rsi_over_70 = sum(1 for _, v in rsi_list if v > 70)

if True:
    print(f"RSI<30: {rsi_under_30} | RSI 40-50: {rsi_40_50} | RSI 50-60: {rsi_50_60} | RSI >70: {rsi_over_70}")

# MACD histogram sign analysis
macd_bullish = sum(1 for r in results.values() 
                   if isinstance(r.get('histogram'), (int, float)) and r['histogram'] > 0)
macd_bearish = sum(1 for r in results.values() 
                   if isinstance(r.get('histogram'), (int, float)) and r['histogram'] < 0)
print(f"MACD bullish(hist>0): {macd_bullish} | bearish: {macd_bearish}")

# MA5 vs MA20 alignment
ma_golden = sum(1 for r in results.values() 
                if isinstance(r.get('ma5'), (int, float)) and isinstance(r.get('ma20'), (int, float)) 
                and r['ma5'] > r['ma20'])
ma_death = sum(1 for r in results.values() 
               if isinstance(r.get('ma5'), (int, float)) and isinstance(r.get('ma20'), (int, float)) 
               and r['ma5'] < r['ma20'])
print(f"MA5>MA20(Golden cross bullish): {ma_golden} | MA5<MA20(Death) bearish: {ma_death}")

# Pocket Pivot potential check  
print("\n=== POCKET PIVOT CANDIDATES ===")
for sym, data in results.items():
    if isinstance(data.get('rsi'), (int, float)) and data['rsi'] < 45:
        if isinstance(data.get('macd'), (int, float)) and data['macd'] > 0:
            print(f"{sym}: RSI={data['rsi']} MACD={data['macd']:+.4f} -> potential pivot candidate")
