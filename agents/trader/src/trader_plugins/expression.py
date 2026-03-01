"""LLM expression layer (voice-only): explain, never mutate, TradePlan."""

from __future__ import annotations

import importlib

from trader_plugins.types import TradePlan


class TraderExpressionLayer:
    """Converts plan/state into concise human explanation text."""

    def __init__(self) -> None:
        self._client = None
        self._openrouter_error = Exception
        try:
            client_module = importlib.import_module("llm_assistant.client")
            config_module = importlib.import_module("llm_assistant.config")
            credentials = config_module.load_openrouter_credentials()
            self._openrouter_error = client_module.OpenRouterError
            if credentials.get("api_key"):
                self._client = client_module.OpenRouterClient(
                    api_key=str(credentials["api_key"]),
                    model=str(credentials["model"]),
                    base_url=str(credentials["base_url"]),
                    timeout_s=float(credentials["timeout_s"]),
                    referer=str(credentials["referer"]),
                    title=str(credentials["title"]),
                )
        except Exception:
            self._client = None

    def explain(self, plan: TradePlan, summary_state: dict[str, object]) -> dict[str, str]:
        """Return explanation text while preserving decision immutability by contract."""
        if self._client is None:
            return {
                "headline": f"{plan.action} {plan.symbol} ({plan.mode})",
                "bullets": (
                    f"p_win={plan.p_win:.2f} threshold={plan.threshold:.2f}; "
                    f"uncertainty={plan.uncertainty:.2f}; gates={plan.reason}."
                ),
                "risk": f"Mode={plan.mode}; dd_day={summary_state.get('dd_day', 0):.3f}",
                "triggers": "Macro regime must remain supportive and guardrails pass.",
            }

        prompt = (
            "Você é camada de expressão. NÃO altere decisão. "
            "Responda JSON com campos headline, bullets, risk, triggers. "
            f"Plano: {plan}. Estado resumido: {summary_state}"
        )
        try:
            text = self._client.generate_reply_sync(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                top_p=0.9,
                presence_penalty=0.0,
            )
            return {
                "headline": f"{plan.action} {plan.symbol}",
                "bullets": text[:600],
                "risk": f"mode={plan.mode}",
                "triggers": "contract: explanation_only",
            }
        except self._openrouter_error:
            return {
                "headline": f"{plan.action} {plan.symbol}",
                "bullets": "LLM indisponível; usando explicação local determinística.",
                "risk": f"mode={plan.mode}",
                "triggers": "contract: explanation_only",
            }
