"""
Backtest: 동일 지표/전략 (처리 순서 스탑→청산→진입, 직전 N봉 Donchian, 필터 3개).
- Binance API 또는 DB 테이블(btc4h 등)에서 캔들 로드 가능.
- 매매 기록 전체를 JSON 파일로 저장 가능.
CLI: python -m app.backtest BTCUSDT 4h --source db --output trades.json
"""
import argparse
import json
import sys
from app.services.binance_client import fetch_klines
from app.services.db_klines import load_klines_from_db
from app.services.indicators import compute_all
from app.services.strategy import evaluate, LONG_ENTRY, SHORT_ENTRY, LONG_EXIT, SHORT_EXIT
from app.services.params import DEFAULT_PARAMS
from app.services.adaptive_filter import evaluate as filter_evaluate, check_consecutive_losses, reason_to_ko


def run_backtest(
    symbol: str,
    tf: str,
    limit: int | None = 500,
    source: str = "binance",
    initial_capital_usdt: float = 1000.0,
    adx_min: float | None = None,
    entry_len: int | None = None,
    exit_len: int | None = None,
    cooldown_bars: int | None = None,
    slippage_bps: float = 0,
    fee_bps: float = 0,
) -> dict:
    """
    source: "binance" | "db"
    - binance: fetch_klines(symbol, tf, limit)
    - db: load_klines_from_db(symbol, tf, limit) — btc4h 등 TABLE_MAP에 등록된 테이블 사용.
    """
    params = dict(DEFAULT_PARAMS)
    if adx_min is not None:
        params["adx_min"] = adx_min
    if entry_len is not None:
        params["entry_len"] = entry_len
    if exit_len is not None:
        params["exit_len"] = exit_len
    if cooldown_bars is not None:
        params["cooldown_bars"] = cooldown_bars

    if source == "db":
        try:
            klines = load_klines_from_db(symbol, tf, limit=limit)
        except Exception as e:
            return {"error": f"DB 로드 실패: {e}"}
    else:
        klines = fetch_klines(symbol, tf, limit=limit or 500)

    if len(klines) < 250:
        return {"error": f"캔들 부족: {len(klines)}개 (최소 250 필요)"}

    ema_len = params["ema_len"]
    entry_len = params["entry_len"]
    exit_len = params["exit_len"]
    dmi_len = params["dmi_len"]
    atr_len = params["atr_len"]
    adx_min = params["adx_min"]
    stop_mult = params["stop_mult"]
    breakout_atr_margin = params.get("breakout_atr_margin", 0.2)
    use_ema_slope = params.get("use_ema_slope", True)
    use_adx_rising = params.get("use_adx_rising", True)
    cooldown_bars = int(params.get("cooldown_bars", 0))  # 청산 후 N봉 대기 (실전과 동일)

    start_idx = max(ema_len, entry_len, exit_len, dmi_len, atr_len) + 25
    position_side = None
    entry_price = 0.0
    stop_price: float | None = None
    trades = []
    balance = initial_capital_usdt
    last_3_exit_pnls: list[float] = []
    skip_entries_remaining = 0
    entry_filter_state = "NORMAL"
    entry_position_mult = 1.0
    last_exit_bar_idx: int | None = None  # 청산 후 N봉 대기용 (실전 worker _in_cooldown과 동일)

    slip = 1 + (slippage_bps / 10000)  # 진입 시 불리, 청산 시 불리
    fee = fee_bps / 10000  # 한 번당

    for i in range(start_idx, len(klines)):
        window = klines[: i + 1]
        indicators = compute_all(
            window,
            ema_len=ema_len,
            entry_len=entry_len,
            exit_len=exit_len,
            dmi_len=dmi_len,
            atr_len=atr_len,
        )
        close = indicators.get("close")
        if close is None:
            continue

        action = evaluate(
            indicators,
            position_side,
            entry_price=entry_price if position_side else None,
            stop_price=stop_price,
            adx_min=adx_min,
            breakout_atr_margin=breakout_atr_margin,
            use_ema_slope=use_ema_slope,
            use_adx_rising=use_adx_rising,
        )

        bar = window[-1]
        high = bar["h"]
        low = bar["l"]
        t = bar["open_time"]

        # Adaptive Filter (거래 여부·규모만 조절, 진입/청산 규칙은 그대로)
        adx = indicators.get("ADX")
        atr_cur = indicators.get("ATR")
        atr_30 = indicators.get("ATR_30")
        filt = filter_evaluate(adx, atr_cur, atr_30, last_3_exit_pnls, skip_entries_remaining)

        def _record_exit(side: str, exit_px: float, pnl_pct: float, via: str):
            nonlocal balance, last_3_exit_pnls, skip_entries_remaining
            balance = balance * (1 + entry_position_mult * pnl_pct / 100)
            last_3_exit_pnls = (last_3_exit_pnls + [pnl_pct])[-3:]
            if check_consecutive_losses(last_3_exit_pnls):
                skip_entries_remaining = 2
            return {"time": t, "side": side, "price": exit_px, "action": "exit", "pnl_pct": pnl_pct, "via": via, "balance": balance, "filter_state": entry_filter_state}

        # 1) 스탑 체결 (봉 중) — 실전과 동일
        if position_side == "LONG" and stop_price is not None and low <= stop_price:
            exit_px = min(stop_price, close) * (1 - fee)
            pnl_pct = (exit_px - entry_price * (1 + fee)) / (entry_price * (1 + fee)) * 100
            trades.append(_record_exit("LONG", exit_px, pnl_pct, "stop"))
            position_side = None
            entry_price = 0.0
            stop_price = None
            last_exit_bar_idx = i
            continue
        if position_side == "SHORT" and stop_price is not None and high >= stop_price:
            exit_px = max(stop_price, close) * (1 + fee)
            pnl_pct = (entry_price * (1 - fee) - exit_px) / (entry_price * (1 - fee)) * 100
            trades.append(_record_exit("SHORT", exit_px, pnl_pct, "stop"))
            position_side = None
            entry_price = 0.0
            stop_price = None
            last_exit_bar_idx = i
            continue

        # 2) 청산 신호 — 실전과 동일
        if action == LONG_EXIT and position_side == "LONG":
            exit_px = close * (1 - fee)
            pnl_pct = (exit_px - entry_price * slip) / (entry_price * slip) * 100
            trades.append(_record_exit("LONG", exit_px, pnl_pct, "channel"))
            position_side = None
            entry_price = 0.0
            stop_price = None
            last_exit_bar_idx = i
            continue
        if action == SHORT_EXIT and position_side == "SHORT":
            exit_px = close * (1 + fee)
            pnl_pct = (entry_price * (1 - fee) - exit_px) / (entry_price * (1 - fee)) * 100
            trades.append(_record_exit("SHORT", exit_px, pnl_pct, "channel"))
            position_side = None
            entry_price = 0.0
            stop_price = None
            last_exit_bar_idx = i
            continue

        # 청산 후 N봉 대기 (실전 worker _in_cooldown과 동일)
        skip_entry_cooldown = (
            last_exit_bar_idx is not None
            and i <= last_exit_bar_idx + 1 + cooldown_bars
        )

        # 3) 진입 (필터 + 청산 후 쿨다운: 실전과 동일)
        if action == LONG_ENTRY and position_side is None and not skip_entry_cooldown:
            if not filt.allowed:
                if filt.reason == "consecutive_loss_cooldown":
                    skip_entries_remaining = max(0, skip_entries_remaining - 1)
                continue
            entry_filter_state = filt.state
            entry_position_mult = filt.multiplier
            atr_val = indicators.get("ATR") or 0
            entry_price = close * slip
            stop_price = entry_price - stop_mult * atr_val
            position_side = "LONG"
            trades.append({"time": t, "side": "LONG", "price": entry_price, "action": "entry", "filter_state": filt.state, "position_mult": filt.multiplier, "reason_ko": reason_to_ko(filt.reason)})
        elif action == SHORT_ENTRY and position_side is None and not skip_entry_cooldown:
            if not filt.allowed:
                if filt.reason == "consecutive_loss_cooldown":
                    skip_entries_remaining = max(0, skip_entries_remaining - 1)
                continue
            entry_filter_state = filt.state
            entry_position_mult = filt.multiplier
            atr_val = indicators.get("ATR") or 0
            entry_price = close * (1 - fee)
            stop_price = entry_price + stop_mult * atr_val
            position_side = "SHORT"
            trades.append({"time": t, "side": "SHORT", "price": entry_price, "action": "entry", "filter_state": filt.state, "position_mult": filt.multiplier, "reason_ko": reason_to_ko(filt.reason)})

    exit_trades = [t for t in trades if t.get("action") == "exit"]
    wins = [t for t in exit_trades if t.get("pnl_pct", 0) > 0]
    total_pnl = sum(t.get("pnl_pct", 0) for t in exit_trades)
    win_rate = round(len(wins) / len(exit_trades) * 100, 2) if exit_trades else 0
    n_bars = len(klines)
    final_balance = balance
    growth_pct = round((final_balance - initial_capital_usdt) / initial_capital_usdt * 100, 2) if initial_capital_usdt else 0

    result_summary = {
        "initial_capital_usdt": initial_capital_usdt,
        "final_balance_usdt": round(final_balance, 2),
        "growth_pct": growth_pct,
        "symbol": symbol,
        "tf": tf,
        "source": source,
        "adaptive_filter": "ON",
        "bars": n_bars,
        "bars_used": n_bars - start_idx,
        "trades_count": len(exit_trades),
        "wins": len(wins),
        "losses": len(exit_trades) - len(wins),
        "win_rate_pct": win_rate,
        "total_pnl_pct": round(total_pnl, 2),
        "avg_pnl_per_trade_pct": round(total_pnl / len(exit_trades), 2) if exit_trades else 0,
    }

    return {
        "result": result_summary,
        "symbol": symbol,
        "tf": tf,
        "source": source,
        "bars": n_bars,
        "start_idx": start_idx,
        "trades_count": len(exit_trades),
        "wins": len(wins),
        "losses": len(exit_trades) - len(wins),
        "win_rate_pct": win_rate,
        "total_pnl_pct": round(total_pnl, 2),
        "params": params,
        "trades": trades,
        "trades_last_20": trades[-20:],
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest strategy (Binance API 또는 DB btc4h)")
    parser.add_argument("symbol", default="BTCUSDT", nargs="?", help="Symbol (default: BTCUSDT)")
    parser.add_argument("tf", default="4h", nargs="?", help="Timeframe (default: 4h)")
    parser.add_argument("--source", choices=("binance", "db"), default="binance", help="캔들 출처: binance API 또는 db(btc4h 등)")
    parser.add_argument("--limit", type=int, default=None, help="캔들 개수 (db일 때 None=전체, binance 기본 500)")
    parser.add_argument("--output", "-o", type=str, default=None, help="매매 기록 전체를 저장할 JSON 파일 경로")
    parser.add_argument("--capital", type=float, default=1000, help="시작 자금 USDT (기본 1000)")
    parser.add_argument("--adx-min", type=float, default=None, help="ADX minimum")
    parser.add_argument("--entry-len", type=int, default=None, help="Donchian entry length")
    parser.add_argument("--exit-len", type=int, default=None, help="Donchian exit length")
    parser.add_argument("--cooldown-bars", type=int, default=None, help="청산 후 N봉 대기 (실전과 동일, 기본 params)")
    parser.add_argument("--slippage-bps", type=float, default=0, help="Slippage bps (e.g. 10 = 0.1%%)")
    parser.add_argument("--fee-bps", type=float, default=5, help="Fee one-way bps (e.g. 5 = 0.05%%)")
    args = parser.parse_args()

    if args.source == "binance" and args.limit is None:
        args.limit = 500

    result = run_backtest(
        args.symbol,
        args.tf,
        limit=args.limit,
        source=args.source,
        initial_capital_usdt=args.capital,
        adx_min=args.adx_min,
        entry_len=args.entry_len,
        exit_len=args.exit_len,
        cooldown_bars=args.cooldown_bars,
        slippage_bps=args.slippage_bps,
        fee_bps=args.fee_bps,
    )
    if "error" in result:
        print(result["error"], file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"매매 기록 저장: {args.output}")
        # 결과 요약만 별도 result.json 저장 (승률, total PnL 등)
        result_path = args.output.rsplit(".", 1)[0] + "_result.json" if "." in args.output else args.output + "_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result["result"], f, ensure_ascii=False, indent=2)
        print(f"결과 요약 저장: {result_path}")

    r = result["result"]
    print("========== 백테스트 결과 ==========")
    print(f"시작 자금: {r['initial_capital_usdt']} USDT  →  최종 잔고: {r['final_balance_usdt']} USDT")
    print(f"상승률: {r['growth_pct']}%")
    print(f"승률: {r['win_rate_pct']}%  (승: {r['wins']} / 패: {r['losses']} / 총 거래: {r['trades_count']})")
    print(f"총 수익률(누적): {r['total_pnl_pct']}%  |  거래당 평균: {r['avg_pnl_per_trade_pct']}%")
    print(f"Symbol: {r['symbol']}  TF: {r['tf']}  Bars: {r['bars']}")
    print("==================================")


if __name__ == "__main__":
    main()
