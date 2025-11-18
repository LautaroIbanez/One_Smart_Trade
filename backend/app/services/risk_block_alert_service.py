"""Service for sending internal alerts when users are blocked by risk or capital validation."""
import os
from typing import Any
import httpx

from app.core.logging import logger


class RiskBlockAlertService:
    """Service for sending alerts when users are blocked by risk or capital validation."""
    
    def __init__(self):
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)
    
    async def send_capital_block_alert(
        self,
        user_id: str,
        context_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Send alert when a user is blocked due to missing capital.
        
        Args:
            user_id: User ID
            context_data: Additional context (has_data, equity, etc.)
        """
        if not self.enabled:
            return
        
        try:
            context = context_data or {}
            equity = context.get("equity")
            has_data = context.get("has_data", False)
            
            payload = {
                "text": "🚫 Usuario Bloqueado: Capital No Validado",
                "attachments": [
                    {
                        "color": "warning",
                        "fields": [
                            {"title": "User ID", "value": user_id, "short": True},
                            {"title": "Tipo de Bloqueo", "value": "Capital No Validado", "short": True},
                            {"title": "Tiene Datos", "value": "Sí" if has_data else "No", "short": True},
                            {"title": "Equity", "value": f"${equity:.2f}" if equity else "N/A", "short": True},
                        ],
                        "footer": "One Smart Trade - Risk Management",
                        "ts": int(__import__("time").time()),
                    }
                ],
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload, timeout=10.0)
                response.raise_for_status()
                logger.info("Capital block alert sent", extra={"user_id": user_id})
        except Exception as exc:
            logger.warning("Failed to send capital block alert", extra={"user_id": user_id, "error": str(exc)}, exc_info=True)
    
    async def send_daily_risk_limit_alert(
        self,
        user_id: str,
        daily_risk_pct: float,
        daily_limit_pct: float,
        context_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Send alert when a user is blocked due to daily risk limit exceeded.
        
        Args:
            user_id: User ID
            daily_risk_pct: Current daily risk percentage
            daily_limit_pct: Daily risk limit percentage
            context_data: Additional context
        """
        if not self.enabled:
            return
        
        try:
            context = context_data or {}
            equity = context.get("equity")
            trades_count = context.get("trades_count")
            
            payload = {
                "text": "🚫 Usuario Bloqueado: Riesgo Diario Excedido",
                "attachments": [
                    {
                        "color": "danger",
                        "fields": [
                            {"title": "User ID", "value": user_id, "short": True},
                            {"title": "Tipo de Bloqueo", "value": "Riesgo Diario Excedido", "short": True},
                            {"title": "Riesgo Actual", "value": f"{daily_risk_pct:.2f}%", "short": True},
                            {"title": "Límite Diario", "value": f"{daily_limit_pct}%", "short": True},
                            {"title": "Equity", "value": f"${equity:.2f}" if equity else "N/A", "short": True},
                            {"title": "Trades Hoy", "value": str(trades_count) if trades_count is not None else "N/A", "short": True},
                        ],
                        "footer": "One Smart Trade - Risk Management",
                        "ts": int(__import__("time").time()),
                    }
                ],
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload, timeout=10.0)
                response.raise_for_status()
                logger.info("Daily risk limit alert sent", extra={"user_id": user_id, "risk_pct": daily_risk_pct})
        except Exception as exc:
            logger.warning("Failed to send daily risk limit alert", extra={"user_id": user_id, "error": str(exc)}, exc_info=True)
    
    async def send_trade_limit_preventive_alert(
        self,
        user_id: str,
        trades_count: int,
        max_trades_24h: int,
        context_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Send alert when a user is blocked due to trade limit preventive.
        
        Args:
            user_id: User ID
            trades_count: Number of trades in last 24h
            max_trades_24h: Maximum allowed trades in 24h
            context_data: Additional context
        """
        if not self.enabled:
            return
        
        try:
            context = context_data or {}
            equity = context.get("equity")
            daily_risk_pct = context.get("daily_risk_pct")
            
            payload = {
                "text": "⏸️ Usuario Bloqueado: Límite Preventivo de Trades",
                "attachments": [
                    {
                        "color": "warning",
                        "fields": [
                            {"title": "User ID", "value": user_id, "short": True},
                            {"title": "Tipo de Bloqueo", "value": "Límite Preventivo", "short": True},
                            {"title": "Trades en 24h", "value": str(trades_count), "short": True},
                            {"title": "Límite Máximo", "value": str(max_trades_24h), "short": True},
                            {"title": "Equity", "value": f"${equity:.2f}" if equity else "N/A", "short": True},
                            {"title": "Riesgo Diario", "value": f"{daily_risk_pct:.2f}%" if daily_risk_pct is not None else "N/A", "short": True},
                        ],
                        "footer": "One Smart Trade - Risk Management",
                        "ts": int(__import__("time").time()),
                    }
                ],
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload, timeout=10.0)
                response.raise_for_status()
                logger.info("Trade limit preventive alert sent", extra={"user_id": user_id, "trades_count": trades_count})
        except Exception as exc:
            logger.warning("Failed to send trade limit preventive alert", extra={"user_id": user_id, "error": str(exc)}, exc_info=True)


# Global instance
risk_block_alert_service = RiskBlockAlertService()

