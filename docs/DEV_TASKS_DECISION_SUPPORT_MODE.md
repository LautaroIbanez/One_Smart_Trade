# Decision-Support Mode Task List

This application is strictly a **decision-support and research dashboard**. It does NOT place live trades. The goal of this task list is to move from an unsafe/experimental state to an honest research dashboard that makes its limitations explicit.

## A. Safety & Guardrails

- When `metrics_status` is not `"PASS"`, both the API and the UI must clearly expose the degraded state and the reason.
- Do not generate synthetic performance metrics when `trade_count == 0`; instead return clear `NO_TRADES` / `no_trades` responses.
- Any dev/test bypass must be explicit (`dev_bypass` metadata) and disabled by default outside test contexts.

## B. Decision-Support Mode / No Live Execution

- Ensure any live trading, execution, or auto-close behavior stays disabled or simulation-only when decision-support flags are enabled.
- Add and honor configuration flags: `DECISION_SUPPORT_ONLY = true` and `DISABLE_LIVE_EXECUTION = true`.
- Propagate these flags through backend execution paths so live-order side effects are skipped, with explicit logging.

## C. UI Clarity & Warnings

- Show a global banner: "Research / decision-support only. No live trades are executed from this app."
- When `metrics_status` is degraded, gray-out / de-emphasize KPIs and show: "Backtest invalid or incomplete (e.g., 0 trades, guardrails bypassed). Use this dashboard only as research, NOT as trading advice."
- Label recommendation signals as "Experimental signal – decision-support only, NOT trading advice" and surface guardrail/fallback reasons when present.

## D. Backtest "0 trades" instrumentation

- Add debug logging for every generated signal (enter/exit/hold/etc.), the resulting order decision, and rejection reasons (zero size, risk checks, missing price, etc.).
- Summarize enter/exit signals, orders created, trades closed, and rejection counts at the end of each backtest run.
- Keep guardrails strict—never fabricate trades or profitability; use diagnostics to explain `trade_count == 0` or `signal_counts.enter > 0` cases.

## Metrics Status Reference (for frontend consumers)

- `PASS`: metrics validated by guardrails.
- `NO_TRADES`: backtest executed but produced zero trades; performance metrics unavailable.
- `INSUFFICIENT_DATA`: fewer trades than minimum guardrail; metrics informational only.
- `DEV_FALLBACK`: dev-mode bypass applied (e.g., min trades); show strong warnings and bypass details.
- `FAIL`: guardrail validation failed; metrics not trustworthy.

