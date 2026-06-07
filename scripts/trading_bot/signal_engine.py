#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine v2.0 (2026-06-05)
Key fixes: 1) support/resistance breakout detection, 2) THRESHOLD=30, 3) ADX before threshold,
4) MACD magnitude weighting, 5) robust candle handling, 6) single-vote signals preserved.
"""

try:
    from config import (
        RSI_OVERBOUGHT, RSI_OVERSOLD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
        MA_SHORT, MA_LONG, VOLUME_RATIO_THRESHOLD, ATR_MULTIPLIER,
        MIN_CONFIDENCE_THRESHOLD, SIGNAL_EMOJIS, PIVOT_LOOKBACK,
    )
except ImportError:
    RSI_OVERBOUGHT = 68
    RSI_OVERSOLD = 32
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    MA_SHORT = 5
    MA_LONG = 20
    VOLUME_RATIO_THRESHOLD = 1.8
    ATR_MULTIPLIER = 2
    MIN_CONFIDENCE_THRESHOLD = 30   # Lowered from 45 (2026-06-05)
    SIGNAL_EMOJIS = {"BUY": "green_circle", "SELL": "red_circle", "HOLD": "white_circle"}
    PIVOT_LOOKBACK = 40


def _detect_breakout(candles, latest_price):
    """Detect breakout above resistance swing high or below support swing low.
    Returns dict with action: 'BUY'/'SELL'/None, reason note."""
    if not candles or len(candles) < 10:
        return None

    curr_close = latest_price
    n = len(candles)

    # Scan last 15 candles for local peaks/troughs (swing highs/lows)
    scan_len = min(15, n)
    swing_highs = []
    swing_lows = []

    for i in range(1, min(scan_len, n) - 1):
        c = candles[i]
        prev_c = candles[max(0, i-1)]
        next_idx = min(i + 1, n - 1)
        next_c = candles[next_idx]

        ph = c.get("h", 0)
        pl = c.get("l", 0)
        range_pct = (ph - pl) / max(pl, 1) * 100 if pl > 0 else 0

        left_ok = ph >= prev_c.get("h", 0)
        right_ok = ph >= next_c.get("h", 0)
        if left_ok and right_ok and range_pct > 0.5:
            swing_highs.append(ph)

        pl_left = prev_c.get("l", 0)
        pl_right = next_c.get("l", 0)
        if pl <= pl_left and pl <= pl_right and range_pct > 0.5:
            swing_lows.append(pl)

    # Fallback: nearest 20-period high/low
    if not swing_highs or not swing_lows:
        recent = candles[-min(20, n):]
        if not swing_highs:
            swing_highs = [max(c.get("h", 0) for c in recent)]
        if not swing_lows:
            swing_lows = [min(c.get("l", 0) for c in recent)]

    # Check if price is within 2% of nearest swing high (breakout zone)
    nearest_sh = None
    nearest_sl = None
    for sh in swing_highs:
        if sh <= curr_close * 1.03 and sh >= curr_close * 0.95:
            if nearest_sh is None or abs(sh - curr_close) < abs(nearest_sh - curr_close):
                nearest_sh = sh

    for sl in swing_lows:
        if sl <= curr_close * 1.03 and sl >= curr_close * 0.96:
            if nearest_sl is None or abs(sl - curr_close) < abs(nearest_sl - curr_close):
                nearest_sl = sl

    result = {}

    # Breakout above resistance (price near swing high, potentially breaking through)
    if nearest_sh and curr_close >= nearest_sh * 0.95:
        break_pct = ((curr_close - nearest_sh) / max(nearest_sh, 1)) * 100
        if break_pct >= -2 and break_pct <= 5:  # Within 2% below to 5% above
            result["action"] = "BUY"
            result["note"] = (
                f"Breakout zone: price {curr_close:.2f} near resistance at {nearest_sh:.2f}"
                + (f" (+{break_pct:+.1f}%)" if break_pct >= 0 else f" ({break_pct:.1f}% before breakout)")
            )
            return result

    # Breakdown below support
    if nearest_sl and curr_close <= nearest_sl * 1.05:
        break_pct = ((nearest_sl - curr_close) / max(nearest_sl, 1)) * 100
        if break_pct >= -2 and break_pct <= 5:
            result["action"] = "SELL"
            result["note"] = (
                f"Breakdown zone: price {curr_close:.2f} near support at {nearest_sl:.2f}"
                + (f" below by {break_pct:.1f}%)" if break_pct >= 0 else "")
            )
            return result

    return None


class SignalEngine:
    """Analyze technical indicators and generate signals Buy/Sell/Hold."""

    def __init__(self, config=None):
        if config:
            self.RSI_OVERBOUGHT = config.get("rsi_overbought", RSI_OVERBOUGHT)
            self.RSI_OVERSOLD = config.get("rsi_oversold", RSI_OVERSOLD)
            self.VOLUME_THRESHOLD = config.get("volume_threshold", VOLUME_RATIO_THRESHOLD)
            self.ATR_MULT = config.get("atr_multiplier", ATR_MULTIPLIER)
        else:
            self.RSI_OVERBOUGHT = RSI_OVERBOUGHT
            self.RSI_OVERSOLD = RSI_OVERSOLD
            self.VOLUME_THRESHOLD = VOLUME_RATIO_THRESHOLD
            self.ATR_MULT = ATR_MULTIPLIER

    def _detect_pocket_pivot(self, candles):
        """Detect Pocket Pivot (Minervini pattern) from OHLCV candles."""
        if not candles or len(candles) < 15:
            return None
        current = candles[-1]
        current_close = current["c"]
        current_open = current["o"]
        current_high = current["h"]
        current_low = current["l"]
        current_volume = max(current.get("v", 0), 1)

        candle_range = current_high - current_low
        bullish_close = (current_close >= current_open) or \
                (candle_range > 0 and current_close > current_low + candle_range * 0.75)
        if not bullish_close:
            return None

        lookback = min(len(candles) - 1, max(PIVOT_LOOKBACK, 20))
        down_days = []
        for i in range(max(3, len(candles) - lookback), len(candles) - 1):
            candle = candles[i]
            if candle["c"] < candle["o"]:
                body_pct = abs(candle["o"] - candle["c"]) / max(candle["c"], 1) * 100
                if body_pct > 0.2:
                    down_days.append({
                        "idx": i,
                        "high": candle["h"],
                        "low": candle["l"],
                        "close": candle["c"],
                        "volume": candle["v"]
                    })

        if not down_days:
            return None

        for dd in reversed(down_days):
            min_breakout = dd["high"] * 1.003
            if current_close < min_breakout:
                continue
            if dd["volume"] <= 0:
                continue
            vol_ratio = current_volume / dd["volume"]
            if vol_ratio < 1.3:
                continue

            break_factor = (current_close - dd["high"]) / max(dd["high"], 1) * 100
            vol_bonus = min(vol_ratio * 3, 15)
            break_bonus = min(break_factor * 5, 20)
            confidence_score = min(45 + vol_bonus + break_bonus, 95)

            return {
                "is_pocket_pivot": True,
                "pivot_day_idx": dd["idx"],
                "pivot_high": round(dd["high"], 2),
                "pivot_close": round(dd["close"], 2),
                "breakout_pct": round(break_factor, 2),
                "volume_ratio": round(vol_ratio, 1),
                "confidence_boost": round(confidence_score),
                "current_volume": current_volume,
                "pivot_volume": dd["volume"],
            }
        return None

    def _calc_bollinger(self, close_prices, period=20):
        """Calculate BB %B and Width Squeeze."""
        step = min(5, period // 4)
        if len(close_prices) < period + step * 2:
            return None

        sma_current = sum(close_prices[-period:]) / period
        stddev_current = (
            sum((x - sma_current) ** 2 for x in close_prices[-period:]) / period
        ) ** 0.5

        upper_band = sma_current + 2 * stddev_current
        lower_band = sma_current - 2 * stddev_current

        widths = []
        end_idx = len(close_prices) - step
        for start in range(step, end_idx, step):
            window = close_prices[start:start + period]
            if len(window) == period:
                sma_w = sum(window) / period
                sd_w = (sum((x - sma_w) ** 2 for x in window) / period) ** 0.5
                widths.append(sma_w * 4 * sd_w)

        current_width = sma_current * 4 * stddev_current
        if widths:
            sorted_widths = sorted(widths)
            rank = sum(1 for w in sorted_widths if w <= current_width)
            width_percentile = (rank / len(sorted_widths)) * 100
        else:
            width_percentile = 50

        band_width_pct = current_width / max(sma_current, 1) * 100
        squeeze_score = min(100 - width_percentile, 100)

        current_close = close_prices[-1]
        band_range_val = upper_band - lower_band
        pct_b = (current_close - lower_band) / band_range_val if band_range_val > 0 else 0.5

        return {
            "pct_b": round(pct_b, 3),
            "band_width_pct": round(band_width_pct, 2),
            "width_percentile": round(width_percentile, 1),
            "squeeze_score": round(squeeze_score, 1),
            "upper_band": round(upper_band, 2),
            "lower_band": round(lower_band, 2),
            "sma": round(sma_current, 2),
        }

    def _calc_adx(self, high_prices, low_prices, close_prices, period=14):
        """Calculate ADX for trend strength."""
        if not high_prices or len(high_prices) < period * 2 + 2:
            return None

        def wilders_smooth(data, length):
            if not data or len(data) < length:
                return data[-1] if data else 0
            avg = sum(data[:length]) / length
            for val in data[length:]:
                avg = (avg * (length - 1) + val) / length
            return avg

        plus_dm, minus_dm, true_ranges = [], [], []
        for i in range(1, len(high_prices)):
            prev_h, prev_l = high_prices[i-1], low_prices[i-1]
            curr_h, curr_l = high_prices[i], low_prices[i]
            move_up = curr_h - prev_h
            move_down = prev_l - curr_l

            plus_dm.append(move_up if move_up > move_down and move_up > 0 else 0)
            minus_dm.append(move_down if move_down > move_up and move_down > 0 else 0)
            tr = max(curr_h - curr_l, abs(curr_h - close_prices[i-1]),
                     abs(curr_l - close_prices[i-1]))
            true_ranges.append(tr)

        if len(true_ranges) < period or len(plus_dm) < period:
            return None

        smoothed_tr = wilders_smooth(true_ranges, period)
        smoothed_plus = wilders_smooth(plus_dm, period)
        smoothed_minus = wilders_smooth(minus_dm, period)

        if smoothed_tr < 0.01:
            return None

        plus_di = smoothed_plus / smoothed_tr * 100
        minus_di = smoothed_minus / smoothed_tr * 100
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = (di_diff / di_sum * 100) if di_sum > 0.01 else 50

        smoothed_dx = wilders_smooth([dx] * min(10, len(high_prices)), max(5, period // 2))

        return {
            "adx": round(smoothed_dx, 1),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
        }

    def analyze_stock(self, stock_data):
        """Analyze all technical indicators for one stock. Returns signal dict or None."""
        if not stock_data or stock_data.get("status") == "error":
            return None

        symbol = stock_data["symbol"]
        latest_price = stock_data.get("latest_price")
        if latest_price is None:
            return None

        signals = []   # Detected indicator directions
        reasons = []   # Human-readable explanation

        # === 1. RSI Analysis ===
        rsi = stock_data.get("rsi_14")
        if rsi is not None:
            if rsi > self.RSI_OVERBOUGHT:
                signals.append("SELL")
                reasons.append(
                    f"RSI({int(self.RSI_OVERBOUGHT)}) at {rsi:.1f} (overbought)"
                    " - potential short-term pullback"
                )
            elif rsi < self.RSI_OVERSOLD:
                signals.append("BUY")
                reasons.append(
                    f"RSI({int(self.RSI_OVERSOLD)}) at {rsi:.1f} (oversold)"
                    " - potential recovery bounce"
                )

        # === 2. MACD Crossover Analysis with magnitude weighting ===
        macd_line = stock_data.get("macd_line")
        signal_line = stock_data.get("signal_line")
        histogram = stock_data.get("histogram")

        if (macd_line is not None and signal_line is not None
                and histogram is not None):
            if macd_line > signal_line and (macd_line - signal_line) > 0.01:
                strength = "strong momentum " if abs(histogram) > 0.5 else ""
                signals.append("BUY")
                reasons.append(
                    f"MACD ({macd_line:.4f}) crossed above Signal ({signal_line:.4f}), "
                    f"Histogram {histogram:.4f} -> {strength}bullish momentum confirmed"
                )
            elif macd_line < signal_line and (signal_line - macd_line) > 0.01:
                strength = " (strong)" if abs(histogram) > 0.5 else ""
                signals.append("SELL")
                reasons.append(
                    f"MACD ({macd_line:.4f}) cut below Signal ({signal_line:.4f}), "
                    f"Histogram negative {histogram:.4f}{strength}-> downward trend likely"
                )

        # === 3. MA Cross (MA5 vs MA20) ===
        ma_5 = stock_data.get("ma_5")
        ma_20 = stock_data.get("ma_20")

        if ma_5 is not None and ma_20 is not None:
            diff_pct = ((ma_5 - ma_20) / ma_20) * 100
            if abs(diff_pct) < 0.3:
                signals.append("WATCH")
                reasons.append(
                    f"MA converging (diff {diff_pct:.2f}%) -- watch for direction change"
                )
            elif diff_pct > 0.3:
                signals.append("BUY")
                reasons.append(
                    f"GOLDEN CROSS (MA5={ma_5:.1f} > MA20={ma_20:.1f}, diff {diff_pct:.2f}%)"
                )
            else:
                signals.append("SELL")
                reasons.append(
                    f"MA trend bearish (MA5={ma_5:.1f} < MA20={ma_20:.1f}, {diff_pct:.2f}%)"
                )

        # === 3.5: Support/Resistance Breakout Detection ===
        candles = stock_data.get("candles", [])
        if candles and len(candles) >= 10:
            try:
                brk = _detect_breakout(candles, latest_price)
                if brk:
                    signals.append(brk['action'])
                    reasons.append(brk['note'])
            except Exception:
                pass

        # === 4. Volume Spike Detection ===
        volume = stock_data.get("volume")
        avg_volume = stock_data.get("avg_volume_10d")
        if (volume is not None and avg_volume is not None and avg_volume > 0):
            volume_ratio = volume / avg_volume
            if volume_ratio > self.VOLUME_THRESHOLD:
                signals.append("BUY")
                reasons.append(
                    f"Volume Spike! {volume:,} vs {volume_ratio:.1f}x avg -- strong money inflow"
                )

        # === 5. ATR stop loss / take profit ===
        atr = stock_data.get("atr_14")
        stop_loss = None
        take_profit = None
        if atr is not None and latest_price:
            stop_loss = round(latest_price - (atr * self.ATR_MULT), 2)
            take_profit = round(latest_price + (atr * self.ATR_MULT * 1.5), 2)

        # === 6. Pocket Pivot Detection ===
        pivot_info = None
        if candles and len(candles) >= 15:
            try:
                pivot_info = self._detect_pocket_pivot(candles)
            except Exception:
                pass
        if (pivot_info and pivot_info.get("is_pocket_pivot")):
            signals.append("BUY")
            has_bullish_ma = ma_5 is not None and ma_5 > stock_data.get("ma_20", 0)
            bonus_str = " + MA5 trending up" if has_bullish_ma else ""
            reasons.append(
                f"POCKET PIVOT! {latest_price} broke above pivot high {pivot_info['pivot_high']}"
                f"{bonus_str} -- strong early-entry signal"
            )

        # === 7. Bollinger Bands (safe on empty candles) ===
        bb_info = None
        try:
            close_prices = [c["c"] for c in candles[-60:] if "c" in c]
            if len(close_prices) >= 41:
                bb_info = self._calc_bollinger(close_prices, period=20)
        except (IndexError, KeyError):
            pass

        if bb_info is not None:
            pct_b = bb_info["pct_b"]
            squeeze_score = bb_info["squeeze_score"]
            if pct_b > 1.0 and squeeze_score < 30:
                signals.append("BUY")
                reasons.append(
                    f"BB BREAKOUT! %B={pct_b:.2f} after squeeze -- momentum breakout"
                )
            elif pct_b < 0.0 and squeeze_score < 30:
                signals.append("SELL")
                reasons.append(
                    f"BB BREAKDOWN! %B={pct_b:.2f} -- breakdown signal"
                )
            elif squeeze_score > 70 and pct_b > 0.3:
                signals.append("WATCH")
                reasons.append(
                    f"BB SQUEEZE! width at {bb_info['width_percentile']}% "
                    "-- expecting breakout soon"
                )

        # === 8. ADX Trend Filter (FIXED: applied BEFORE threshold check) ===
        adx_info = None
        try:
            high_prices = [c["h"] for c in candles[-60:] if "h" in c]
            low_prices = [c["l"] for c in candles[-60:] if "l" in c]
            close_prices_2 = [c["c"] for c in candles[-60:] if "c" in c]
            if len(high_prices) >= 30:
                adx_info = self._calc_adx(high_prices, low_prices,
                                          close_prices_2, period=14)
        except (IndexError, KeyError, TypeError):
            pass

        # --- AGGREGATION: Voting system with ADX boost BEFORE threshold ---
        buy_votes = signals.count("BUY")
        sell_votes = signals.count("SELL")
        watch_votes = signals.count("WATCH")
        total_signals = len(signals)

        adx_boost = 0
        if adx_info is not None:
            adx_val = adx_info["adx"]
            plus_di = adx_info["plus_di"]
            minus_di = adx_info["minus_di"]
            if adx_val > 25:
                adx_boost = +10
                reasons.append(
                    f"ADX={adx_val:.1f} (strong trend) +DI={plus_di:.1f}/-DI={minus_di:.1f}"
                )
            elif adx_val < 18:
                adx_boost = -5
                reasons.append(f"ADX={adx_val:.1f} (weak/choppy)")
            else:
                reasons.append(f"ADX={adx_val:.1f} (neutral trend)")
        # Note: "no signal" message suppressed if any indicators detected

        final_signal = "HOLD"
        confidence = 0

        if buy_votes >= 2:
            final_signal = "BUY"
            confidence = min(buy_votes / max(total_signals, 1) * 100 + watch_votes * 10, 98)
            confidence += adx_boost
            if pivot_info and buy_votes >= 2:
                confidence = min(confidence + 5, 98)

        elif sell_votes >= 2:
            final_signal = "SELL"
            confidence = min(sell_votes / max(total_signals, 1) * 100 + watch_votes * 10, 98)
            confidence += adx_boost

        elif buy_votes >= 1:
            final_signal = "BUY"
            confidence = min(40 + watch_votes * 15, 70)
            confidence += adx_boost

        elif sell_votes >= 1:
            final_signal = "SELL"
            confidence = min(35 + watch_votes * 10, 65)
            confidence -= abs(adx_boost) if adx_boost < 0 else 0

        elif buy_votes >= 1 and sell_votes >= 1:
            winner = "BUY" if buy_votes > sell_votes else "SELL"
            final_signal = winner
            confidence = min(max(buy_votes, sell_votes) / max(total_signals, 1) * 50 + watch_votes * 5, 60)
            confidence += (adx_boost if winner == "BUY" and adx_boost > 0 else 0)

        else:
            final_signal = "HOLD"
            confidence = 0
            signals = []
            reasons = []

        # No signal but indicators present -> note the ranging market state
        if confidence == 0:
            has_indicators = rsi is not None or macd_line is not None
            if has_indicators:
                reasons.append("Market in range-bound mode -- waiting for breakout")

        # === THRESHOLD CHECK (FIXED v2.0: applied AFTER ADX boost + any votes) ===
        if confidence < MIN_CONFIDENCE_THRESHOLD and len(signals) > 0:
            final_signal = "HOLD"
            confidence = 0
            signals = []
            reasons.append("Below signal threshold - hold watchlist for next scan")

        return {
            "symbol": symbol,
            "latest_price": latest_price,
            "signal": final_signal,
            "confidence": round(confidence, 1),
            "directions": signals,
            "reasons": reasons,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rsi": rsi,
            "macd": macd_line,
            "atr": atr,
            "pivot_info": pivot_info,
            "bb_info": bb_info,
            "adx_info": adx_info,
        }

    def analyze_batch(self, stocks_data):
        """Analyze multiple stocks. Returns only non-HOLD signals sorted by confidence."""
        results = []
        for stock_data in stocks_data:
            try:
                signal = self.analyze_stock(stock_data)
                if signal and signal["signal"] != "HOLD":
                    results.append(signal)
            except Exception as e:
                print(f"[ERROR] Analyzing {stock_data.get('symbol', '?')}: {e}")

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results


if __name__ == "__main__":
    from market_data import fetch_stock_data
    engine = SignalEngine()
    for sym in ["VCI", "VIC", "VCB"]:
        data = fetch_stock_data(sym)
        sig = engine.analyze_stock(data)
        print(f"{sym}: signal={sig['signal']} conf={sig['confidence']}% rsi={sig.get('rsi')}")
        for r in sig['reasons'][:3]:
            print(f"  - {r}")

