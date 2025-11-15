    def _calculate_theoretical_entry_delta(self, position: dict[str, Any], bar: pd.Series) -> float:
        """Calculate theoretical capital delta for position entry (no frictions)."""
        if not position or position.get("filled_size", 0.0) <= 0:
            return 0.0
        
        size = position.get("filled_size", 0.0)
        entry_price = position.get("entry_price", 0.0)
        
        if position["side"] == "BUY":
            # Theoretical: buy at entry price, no commission
            return -entry_price * size
        else:  # SELL
            # Theoretical: sell at entry price, no commission
            return entry_price * size
    
    def _calculate_theoretical_exit_pnl(
        self, position: dict[str, Any], exit_price: float, exit_reason: str
    ) -> float:
        """Calculate theoretical P&L for position exit (no frictions)."""
        if not position or position.get("filled_size", 0.0) <= 0:
            return 0.0
        
        size = position.get("filled_size", 0.0)
        entry_price = position.get("entry_price", 0.0)
        
        if position["side"] == "BUY":
            # Theoretical: sell at exit price, no commission
            return exit_price * size
        else:  # SELL
            # Theoretical: buy back at exit price, no commission
            return -exit_price * size
    
    def _attempt_theoretical_pending_entry(
        self, position: dict[str, Any], bar: pd.Series, prev_row: pd.Series
    ) -> float:
        """Attempt theoretical pending entry fill (no frictions)."""
        if position.get("pending_size", 0.0) <= 0:
            return 0.0
        
        # Theoretical: always fills at target price
        target_price = position.get("desired_price", bar["open"])
        pending_size = position["pending_size"]
        
        if position["side"] == "BUY":
            return -target_price * pending_size
        else:  # SELL
            return target_price * pending_size
