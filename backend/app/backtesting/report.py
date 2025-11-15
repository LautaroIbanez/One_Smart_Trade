def _render_operational_section(operational_report: dict[str, Any] | None) -> str:
    """Render operational flow section with fill rates, tracking error, and stop rebalancing."""
    if not operational_report:
        return "## Flujo Operativo\n\n*No operational data available.*\n\n"
    
    section = "## Flujo Operativo\n\n"
    section += "*Ingesta → Preprocesamiento → Simulación → Rebalanceo de Stops → Reportes*\n\n"
    
    # Execution metrics
    execution = operational_report.get("execution", {})
    if execution:
        section += "### Ejecución\n\n"
        section += f"- **Fill Rate**: {execution.get('fill_rate', 0.0):.2%}\n"
        section += f"- **Cancel Ratio**: {execution.get('cancel_ratio', 0.0):.2%}\n"
        section += f"- **No-Trade Ratio**: {execution.get('no_trade_ratio', 0.0):.2%}\n"
        section += f"- **Avg Wait Bars**: {execution.get('avg_wait_bars', 0.0):.2f}\n"
        section += f"- **Avg Slippage**: {execution.get('avg_slippage_bps', 0.0):.2f} bps\n\n"
    
    # Realized slippage
    realized_slippage = operational_report.get("realized_slippage")
    if realized_slippage:
        section += "### Slippage Realizado\n\n"
        section += f"- **Promedio**: {realized_slippage.get('avg_bps', 0.0):.2f} bps\n"
        section += f"- **Mediana**: {realized_slippage.get('median_bps', 0.0):.2f} bps\n"
        section += f"- **P95**: {realized_slippage.get('p95_bps', 0.0):.2f} bps\n"
        section += f"- **Máximo**: {realized_slippage.get('max_bps', 0.0):.2f} bps\n\n"
    
    # Fill ratios
    fill_ratios = operational_report.get("fill_ratios")
    if fill_ratios:
        section += "### Fill Ratios\n\n"
        section += f"- **Promedio**: {fill_ratios.get('avg', 0.0):.2%}\n"
        section += f"- **Completos**: {fill_ratios.get('complete_fills', 0)}\n"
        section += f"- **Parciales**: {fill_ratios.get('partial_fills', 0)}\n"
        section += f"- **Fallidos**: {fill_ratios.get('failed_fills', 0)}\n\n"
    
    # Tracking error
    tracking_error = operational_report.get("tracking_error")
    if tracking_error:
        section += "### Tracking Error vs Teórico\n\n"
        section += f"- **Correlación**: {tracking_error.get('correlation', 0.0):.4f}\n"
        section += f"- **Desviación Media**: {tracking_error.get('mean_deviation', 0.0):.4f}\n"
        section += f"- **Máxima Divergencia**: {tracking_error.get('max_divergence', 0.0):.4f}\n"
        section += f"- **Tracking Sharpe**: {tracking_error.get('tracking_sharpe', 0.0):.4f}\n\n"
    
    # Stop rebalancing
    stop_rebalancing = operational_report.get("stop_rebalancing", {})
    if stop_rebalancing:
        total_rebalances = stop_rebalancing.get("total_rebalances", 0)
        section += f"### Rebalanceo de Stops\n\n"
        section += f"- **Total Rebalances**: {total_rebalances}\n"
        
        history = stop_rebalancing.get("rebalance_history", [])
        if history:
            section += f"\n**Últimos {min(5, len(history))} rebalances:**\n\n"
            for event in history[:5]:
                section += f"- **{event.get('timestamp', 'N/A')}** | "
                section += f"Fill: {event.get('fill_price', 0.0):.2f} | "
                if event.get("old_stop_loss") != event.get("new_stop_loss"):
                    section += f"SL: {event.get('old_stop_loss', 0.0):.2f} → {event.get('new_stop_loss', 0.0):.2f} | "
                if event.get("old_take_profit") != event.get("new_take_profit"):
                    section += f"TP: {event.get('old_take_profit', 0.0):.2f} → {event.get('new_take_profit', 0.0):.2f} | "
                section += f"Razón: {event.get('reason', 'N/A')}\n"
            section += "\n"
    
    # Orderbook metrics
    orderbook_metrics = operational_report.get("orderbook_metrics")
    if orderbook_metrics:
        section += "### Métricas de Order Book\n\n"
        section += f"- **Avg Spread**: {orderbook_metrics.get('avg_spread_bps', 0.0):.2f} bps\n"
        section += f"- **Avg Imbalance**: {orderbook_metrics.get('avg_imbalance_pct', 0.0):.2f}%\n\n"
    
    return section
