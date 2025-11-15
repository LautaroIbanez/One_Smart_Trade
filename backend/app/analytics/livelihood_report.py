from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class AccountScenario:
    capital: float
    monthly_income_p10: float
    monthly_income_p50: float
    monthly_income_p90: float
    negative_month_prob: float
    sustainable_capital: float


class LivelihoodReport:
    def build(self, monthly_returns: pd.Series, expenses_target: float) -> list[AccountScenario]:
        scenarios: list[AccountScenario] = []
        for capital in (1_000, 4_000, 10_000, 50_000):
            incomes = monthly_returns * capital
            scenario = AccountScenario(
                capital=float(capital),
                monthly_income_p10=float(incomes.quantile(0.1)) if not incomes.empty else 0.0,
                monthly_income_p50=float(incomes.quantile(0.5)) if not incomes.empty else 0.0,
                monthly_income_p90=float(incomes.quantile(0.9)) if not incomes.empty else 0.0,
                negative_month_prob=float((incomes < 0).mean()) if not incomes.empty else 0.0,
                sustainable_capital=self._capital_for_target(monthly_returns, expenses_target),
            )
            scenarios.append(scenario)
        return scenarios

    def _capital_for_target(self, returns: pd.Series, target: float) -> float:
        if target <= 0:
            return 0.0
        mean_return = float(returns.mean()) if not returns.empty else 0.0
        if mean_return <= 0:
            return float("inf")
        return float(target / mean_return)


