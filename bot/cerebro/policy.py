from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from ..sls_bot import ia_signal_engine
except ImportError:  # pragma: no cover
    from sls_bot import ia_signal_engine  # type: ignore


@dataclass
class PolicyDecision:
    symbol: str
    timeframe: str
    action: str
    confidence: float
    risk_pct: float
    leverage: int
    summary: str
    evidences: Dict[str, float]
    price: float
    stop_loss: float
    take_profit: float
    metadata: Dict[str, Any]
    reasons: list[str]


class PolicyEnsemble:
    """Combina heuristicas, noticias y el motor ML existente."""

    def __init__(self, min_confidence: float, sl_atr: float, tp_atr: float, model_path: str | Path | None = None):
        self.min_confidence = min_confidence
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr
        self._model_artifact = self._load_model(model_path)

    def decide(
        self,
        *,
        symbol: str,
        timeframe: str,
        market_row: dict,
        news_sentiment: float | None = None,
        memory_stats: dict | None = None,
        session_context: dict | None = None,
        news_meta: dict | None = None,
        anomaly_score: float | None = None,
        min_confidence_override: float | None = None,
        normalized_features: dict | None = None,
        exploration_mode: bool = False,
        macro_context: dict | None = None,
        orderflow_context: dict | None = None,
    ) -> PolicyDecision:
        payload, evid_rules, meta = ia_signal_engine.decide(symbol=symbol, marco=timeframe)
        risk_pct = float(payload["riesgo_pct"])
        decision = payload["decision"]
        confidence = payload["confianza_pct"] / 100.0
        if news_sentiment is not None:
            if decision == "LONG":
                confidence = max(0.0, confidence + news_sentiment * 0.05)
            elif decision == "SHORT":
                confidence = max(0.0, confidence - news_sentiment * 0.05)
        threshold = min_confidence_override or self.min_confidence
        exploration_triggered = False
        if confidence < threshold:
            if exploration_mode:
                long_score = evid_rules["rules"]["long"]
                short_score = evid_rules["rules"]["short"]
                fallback = "LONG" if long_score >= short_score else "SHORT"
                decision = fallback
                confidence = max(confidence, threshold * 0.85)
                risk_pct = max(0.1, risk_pct * 0.5)
                exploration_triggered = True
            else:
                decision = "NO_TRADE"

        price = float(market_row.get("close") or 0.0)
        atr = float(market_row.get("atr") or price * 0.005)
        if atr <= 0:
            atr = max(price * 0.005, 0.1)
        if decision == "LONG":
            stop_loss = max(0.0, price - atr * self.sl_atr)
            take_profit = price + atr * self.tp_atr
        else:
            stop_loss = price + atr * self.sl_atr
            take_profit = max(0.0, price - atr * self.tp_atr)

        reasons = [
            f"Rules long/short={evid_rules['rules']['long']:.2f}/{evid_rules['rules']['short']:.2f}",
            f"Confianza modelo={confidence:.2f}",
        ]
        if news_sentiment is not None:
            reasons.append(f"Sentimiento noticias={news_sentiment:+.2f}")
        if anomaly_score is not None:
            reasons.append(f"Anomaly z-score={anomaly_score:.2f}")

        memory_stats = memory_stats or {}
        if memory_stats.get("total", 0) >= 20:
            win_rate = float(memory_stats.get("win_rate") or 0.0)
            dyn_mult = max(0.5, min(1.5, 0.5 + win_rate))
            risk_pct = max(0.1, risk_pct * dyn_mult)
            reasons.append(f"Ajuste riesgo (win_rate={win_rate:.2%}, mult={dyn_mult:.2f})")

        metadata: Dict[str, Any] = {
            "news_sentiment": news_sentiment or 0.0,
            "memory_win_rate": float(memory_stats.get("win_rate") or 0.0),
            "exploration_mode": exploration_mode,
            "exploration_triggered": exploration_triggered,
        }
        if news_meta:
            metadata["news"] = news_meta
        if macro_context:
            metadata["macro"] = macro_context
            macro_score = float(macro_context.get("score", 0.0))
            macro_direction = str(macro_context.get("direction") or "neutral")
            reasons.append(f"Macro score={macro_score:+.2f}")
            if decision in {"LONG", "SHORT"} and macro_direction in {"bullish", "bearish"}:
                conflict = (decision == "LONG" and macro_direction == "bearish") or (
                    decision == "SHORT" and macro_direction == "bullish"
                )
                if conflict:
                    decision = "NO_TRADE"
                    reasons.append("Macro bloquea la operación")
                else:
                    if (decision == "LONG" and macro_direction == "bullish") or (
                        decision == "SHORT" and macro_direction == "bearish"
                    ):
                        risk_pct = min(risk_pct * 1.1, payload["riesgo_pct"] * 1.6)
                        reasons.append("Macro acompaña al trade, riesgo ligeramente mayor")
                    else:
                        risk_pct = max(0.1, risk_pct * 0.85)
                        reasons.append("Macro neutraliza parcialmente, riesgo reducido")
            elif macro_direction == "bearish" and decision == "NO_TRADE" and macro_score < -0.4:
                risk_pct = max(0.1, risk_pct * 0.8)
                reasons.append("Macro reduce riesgo por sesgo bajista")

        if orderflow_context:
            metadata["orderflow"] = orderflow_context
            imbalance = float(orderflow_context.get("liquidity_imbalance") or 0.0)
            spread = float(orderflow_context.get("spread") or 0.0)
            best_bid = float(orderflow_context.get("best_bid") or 0.0)
            best_ask = float(orderflow_context.get("best_ask") or 0.0)
            if decision in {"LONG", "SHORT"} and imbalance:
                if imbalance > 0.25:
                    if decision == "LONG":
                        confidence = min(1.0, confidence + 0.05)
                        risk_pct = min(risk_pct * 1.05, payload["riesgo_pct"] * 1.5)
                        reasons.append("Orderflow acompaña (imbalance +)")
                    else:
                        confidence = max(0.0, confidence - 0.05)
                        risk_pct = max(0.1, risk_pct * 0.8)
                        reasons.append("Orderflow contradice SHORT (imbalance +)")
                elif imbalance < -0.25:
                    if decision == "SHORT":
                        confidence = min(1.0, confidence + 0.05)
                        risk_pct = min(risk_pct * 1.05, payload["riesgo_pct"] * 1.5)
                        reasons.append("Orderflow acompaña (imbalance -)")
                    else:
                        confidence = max(0.0, confidence - 0.05)
                        risk_pct = max(0.1, risk_pct * 0.8)
                        reasons.append("Orderflow contradice LONG (imbalance -)")
            if spread and best_bid and best_ask:
                spread_pct = spread / max((best_bid + best_ask) / 2.0, 1e-9)
                if spread_pct > 0.001:  # 0.1%
                    risk_pct = max(0.1, risk_pct * 0.9)
                    reasons.append(f"Spread amplio ({spread_pct*100:.2f}%) reduce riesgo")
        if session_context:
            metadata["session_guard"] = session_context
            guard_state = session_context.get("state")
            guard_reason = session_context.get("reason")
            session_name = session_context.get("session_name", "Sesion")
            base_action = decision
            if guard_reason:
                reasons.append(guard_reason)
            if guard_state in {"pre_open", "news_wait"}:
                decision = "NO_TRADE"
            elif guard_state == "news_ready":
                risk_mult = float(session_context.get("risk_multiplier") or 1.0)
                news_dir = session_context.get("news_direction")
                if base_action in {"LONG", "SHORT"}:
                    conflict = (base_action == "LONG" and news_dir == "bearish") or (
                        base_action == "SHORT" and news_dir == "bullish"
                    )
                    if conflict:
                        decision = "NO_TRADE"
                        reasons.append(f"{session_name}: noticia {news_dir} contradice {base_action}")
                    else:
                        risk_pct = max(0.1, risk_pct * risk_mult)
                        reasons.append(f"{session_name}: riesgo ajustado x{risk_mult:.2f} tras apertura")
                else:
                    risk_pct = max(0.1, risk_pct * risk_mult)

        ml_features = {
            "confidence": confidence,
            "risk_pct": risk_pct,
            "leverage": float(payload["leverage"]),
            "news_sentiment": news_sentiment or 0.0,
            "session_guard_risk_multiplier": float((session_context or {}).get("risk_multiplier") or 1.0),
            "memory_win_rate": float(memory_stats.get("win_rate") or 0.0),
            "session_guard_penalty": 1.0 if (session_context or {}).get("state") in {"pre_open", "news_wait"} else 0.0,
        }
        if normalized_features:
            ml_features.update({f"norm_{k}": v for k, v in normalized_features.items()})
        if anomaly_score is not None:
            ml_features["anomaly_score"] = anomaly_score
        ml_score = self._score_with_model(ml_features)
        if ml_score is not None and self._model_artifact:
            metadata["ml_score"] = ml_score
            metadata["model_version"] = self._model_artifact.get("version")
            metadata["model_metrics"] = self._model_artifact.get("metrics")
            metadata["action_source"] = "ml"
            reasons.append(f"Modelo entrenado score={ml_score:.2f}")
            confidence = (confidence + ml_score) / 2.0
            if ml_score < 0.4:
                risk_pct = max(0.05, risk_pct * 0.7)
                reasons.append("Modelo reduce riesgo por score bajo")
            elif ml_score > 0.65:
                risk_pct = min(risk_pct * 1.15, payload["riesgo_pct"] * 1.5)
                reasons.append("Modelo permite subir riesgo por score alto")
            metadata["ml_override"] = ml_score > 0.65 or ml_score < 0.4
        else:
            metadata["action_source"] = "heuristic"

        return PolicyDecision(
            symbol=symbol.upper(),
            timeframe=timeframe,
            action=decision,
            confidence=confidence,
            risk_pct=risk_pct,
            leverage=payload["leverage"],
            summary=payload["resumen"],
            evidences={"rules_long": evid_rules["rules"]["long"], "rules_short": evid_rules["rules"]["short"]},
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata,
            reasons=reasons,
        )

    # ----- Modelo entrenado -----
    def _load_model(self, model_path: str | Path | None) -> Optional[dict]:
        if not model_path:
            return None
        path = Path(model_path)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            features = data.get("features") or []
            if not isinstance(features, list):
                return None
            return data
        except Exception:
            return None

    def _score_with_model(self, features: Dict[str, float]) -> Optional[float]:
        if not self._model_artifact:
            return None
        total = 0.0
        meta = self._model_artifact
        feature_defs = meta.get("features") or []
        if not feature_defs:
            return None
        for fdef in feature_defs:
            name = fdef.get("name")
            if not name:
                continue
            val = float(features.get(name, fdef.get("default", 0.0)))
            mean = float(fdef.get("mean") or 0.0)
            std = float(fdef.get("std") or 1.0)
            if std == 0:
                std = 1.0
            norm = (val - mean) / std
            total += norm * float(fdef.get("weight") or 0.0)
        bias = float(meta.get("bias") or 0.0)
        try:
            z = bias + total
            return 1.0 / (1.0 + math.exp(-z))
        except OverflowError:
            return None
