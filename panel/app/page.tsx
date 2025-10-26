"use client";

import React, { useEffect, useMemo, useState } from "react";
import Card from "./components/Card";
import Controls from "./components/Controls";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8880";
const PANEL_TOKEN = process.env.NEXT_PUBLIC_PANEL_API_TOKEN;

type ServiceStatus = { active: boolean; detail?: string };
type StatusResp = {
  services: Record<string, ServiceStatus>;
  bot: any;
};
type SymbolPnl = { symbol: string; pnl_eur: number; fees_eur?: number | null; trades?: number | null };
type PnlItem = { day: string; pnl_eur: number; from_fills?: boolean; symbols?: SymbolPnl[] };
type LogResp = { lines: string[] };
type DecisionRow = { ts?: string; symbol?: string; side?: string; confidence?: number };
type DecisionsResp = { rows: DecisionRow[] };
type SessionGuardMeta = {
  session_name?: string;
  state?: "pre_open" | "news_wait" | "news_ready" | string;
  reason?: string;
  block_trade?: boolean;
  should_close_positions?: boolean;
  minutes_to_open?: number | null;
  minutes_since_open?: number | null;
  news_direction?: string | null;
  news_is_fresh?: boolean;
};
type NewsMeta = {
  latest_title?: string | null;
  latest_url?: string | null;
  latest_ts?: string | null;
  is_fresh?: boolean;
};
type DecisionMetadata = {
  news_sentiment?: number | null;
  news?: NewsMeta | null;
  session_guard?: SessionGuardMeta | null;
};
type CerebroHistoryEntry = {
  ts: string;
  symbol: string;
  timeframe: string;
  confidence?: number;
  risk_pct?: number;
};
type CerebroDecision = {
  action: string;
  confidence: number;
  risk_pct: number;
  leverage: number;
  summary: string;
  reasons?: string[];
  generated_at?: number;
  metadata?: DecisionMetadata | null;
};
type CerebroStatus = {
  ok?: boolean;
  enabled?: boolean;
  time?: string;
  decisions?: Record<string, CerebroDecision>;
  history?: CerebroHistoryEntry[];
  memory?: { total?: number; win_rate?: number };
};
type RiskStateDetails = {
  consecutive_losses?: number;
  cooldown_until_ts?: number;
  active_cooldown_reason?: string | null;
  cooldown_history?: { ts: string; reason: string; minutes: number }[];
  recent_results?: { ts?: number; pnl?: number }[];
  dynamic_risk?: {
    enabled?: boolean;
    multiplier?: number;
    current_equity?: number;
    start_equity?: number;
  };
};

const describeSessionGuard = (guard?: SessionGuardMeta | null) => {
  if (!guard) return null;
  const base = guard.session_name ?? "Sesion";
  switch (guard.state) {
    case "pre_open":
      return `${base} pre-open`;
    case "news_wait":
      return `${base} espera noticia`;
    case "news_ready":
      return `${base} apertura ok`;
    default:
      return base;
  }
};

const classifySentiment = (score?: number | null) => {
  if (typeof score !== "number" || Number.isNaN(score)) return null;
  if (score > 0.05) return { label: "Noticia bullish", className: "ok" };
  if (score < -0.05) return { label: "Noticia bearish", className: "fail" };
  return { label: "Noticia neutral", className: "muted" };
};

const formatNewsAge = (iso?: string | null) => {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  const diffMinutes = Math.max(0, Math.floor((Date.now() - ts) / 60000));
  if (diffMinutes < 1) return "ahora";
  if (diffMinutes < 60) return `${diffMinutes}m`;
  const hours = Math.floor(diffMinutes / 60);
  const mins = diffMinutes % 60;
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
};

const formatEquity = (value?: number | null) => {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(2);
};

const mergeHistory = (current: CerebroHistoryEntry[], incoming: CerebroHistoryEntry[] | undefined) => {
  if (!incoming?.length) return current;
  const seen = new Set(current.map((item) => `${item.symbol}-${item.timeframe}-${item.ts}`));
  const merged = [...current];
  incoming.forEach((entry) => {
    const key = `${entry.symbol}-${entry.timeframe}-${entry.ts}`;
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(entry);
    }
  });
  return merged.slice(-60);
};

export default function Page() {
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [decisiones, setDecisiones] = useState<DecisionRow[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [pnl, setPnl] = useState<PnlItem[]>([]);
  const [cerebro, setCerebro] = useState<CerebroStatus | null>(null);
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [timeframeFilter, setTimeframeFilter] = useState<string>("ALL");
  const [confidenceHistory, setConfidenceHistory] = useState<CerebroHistoryEntry[]>([]);
  const [forceStatus, setForceStatus] = useState<{ state: "idle" | "loading" | "ok" | "error"; message?: string }>({
    state: "idle",
  });

  async function loadAll() {
    try {
      const init = PANEL_TOKEN ? { headers: { "X-Panel-Token": PANEL_TOKEN } } : undefined;
      const [s, d, l, p, ce] = await Promise.all([
        fetch(`${API_BASE}/status`, init).then((r) => r.json()),
        fetch(`${API_BASE}/decisiones?limit=25`, init).then((r) => r.json()),
        fetch(`${API_BASE}/logs/bridge?limit=200`, init).then((r) => r.json()),
        fetch(`${API_BASE}/pnl/diario?days=7`, init).then((r) => r.json()),
        fetch(`${API_BASE}/cerebro/status`, init).then((r) => r.json()).catch(() => null),
      ]);
      setStatus(s);
      setDecisiones((d as DecisionsResp).rows || []);
      setLogs((l as LogResp).lines || []);
      setPnl(p.days || []);
      if (ce) {
        setCerebro(ce);
        setConfidenceHistory((prev) => mergeHistory(prev, ce.history));
      }
    } catch {
      // silencioso para no antagonizar la UI
    }
  }

  async function forceDecision() {
    const symbol = symbolFilter === "ALL" ? availableSymbols[0] : symbolFilter;
    const timeframe = timeframeFilter === "ALL" ? availableTimeframes[0] : timeframeFilter;
    if (!symbol || !timeframe) {
      setForceStatus({ state: "error", message: "Seleccione símbolo y timeframe" });
      return;
    }
    try {
      setForceStatus({ state: "loading" });
      const init =
        PANEL_TOKEN && PANEL_TOKEN.length
          ? {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Panel-Token": PANEL_TOKEN,
              },
              body: JSON.stringify({ symbol, timeframe }),
            }
          : {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ symbol, timeframe }),
            };
      const resp = await fetch(`${API_BASE}/cerebro/decide`, init);
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail?.detail || "Error remoto");
      }
      const data = await resp.json();
      setForceStatus({ state: "ok", message: `Acción ${data.action} con ${Math.round((data.confidence ?? 0) * 100)}%` });
      loadAll();
    } catch (err: any) {
      setForceStatus({ state: "error", message: err?.message || "No se pudo forzar decisión" });
    }
  }

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 5000);
    return () => clearInterval(id);
  }, []);

  const decisionEntries = useMemo(() => Object.entries(cerebro?.decisions || {}), [cerebro]);
  const availableSymbols = useMemo(() => {
    const set = new Set<string>();
    decisionEntries.forEach(([key]) => {
      const [sym] = key.split("::");
      if (sym) set.add(sym);
    });
    return Array.from(set).sort();
  }, [decisionEntries]);
  const availableTimeframes = useMemo(() => {
    const set = new Set<string>();
    decisionEntries.forEach(([key]) => {
      const [, tf = ""] = key.split("::");
      if (tf) set.add(tf);
    });
    return Array.from(set).sort();
  }, [decisionEntries]);
  const filteredEntries = useMemo(() => {
    return decisionEntries.filter(([key]) => {
      const [sym, tf = ""] = key.split("::");
      const symOk = symbolFilter === "ALL" || sym === symbolFilter;
      const tfOk = timeframeFilter === "ALL" || tf === timeframeFilter;
      return symOk && tfOk;
    });
  }, [decisionEntries, symbolFilter, timeframeFilter]);
  const filteredHistory = useMemo(() => {
    return confidenceHistory.filter((entry) => {
      const symOk = symbolFilter === "ALL" || entry.symbol === symbolFilter;
      const tfOk = timeframeFilter === "ALL" || entry.timeframe === timeframeFilter;
      return symOk && tfOk;
    });
  }, [confidenceHistory, symbolFilter, timeframeFilter]);
  const chartPoints = useMemo(() => {
    if (!filteredHistory.length) return "";
    const maxIndex = Math.max(filteredHistory.length - 1, 1);
    return filteredHistory
      .map((entry, idx) => {
        const x = (idx / maxIndex) * 100;
        const confidence = entry.confidence ?? 0.5;
        const y = 100 - Math.min(Math.max(confidence, 0), 1) * 100;
        return `${x},${y}`;
      })
      .join(" ");
  }, [filteredHistory]);

  useEffect(() => {
    if (symbolFilter === "ALL" && availableSymbols.length) {
      setSymbolFilter(availableSymbols[0]);
    }
  }, [availableSymbols, symbolFilter]);

  useEffect(() => {
    if (timeframeFilter === "ALL" && availableTimeframes.length) {
      setTimeframeFilter(availableTimeframes[0]);
    }
  }, [availableTimeframes, timeframeFilter]);

  const slsActive = !!status?.services?.["sls-bot"]?.active;
  const aiActive = !!status?.services?.["ai-bridge"]?.active;
  const riskDetails: RiskStateDetails | undefined = status?.bot?.risk_state_details;
  const cooldownSeconds = riskDetails?.cooldown_until_ts
    ? Math.max(0, riskDetails.cooldown_until_ts - Math.floor(Date.now() / 1000))
    : 0;
  const formatDuration = (seconds: number) => {
    if (seconds <= 0) return "0m";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    if (mins >= 60) {
      const hours = Math.floor(mins / 60);
      const remMins = mins % 60;
      return `${hours}h ${remMins}m`;
    }
    return `${mins}m ${secs}s`;
  };

  return (
    <>
      <h1>SLS Panel</h1>

      <Card title="Servicios">
        <div className="svc-grid">
          <div className="svc-col">
            <div className="svc-head">API (sls-bot)</div>
            <Controls service="sls-bot" />
          </div>
          <div className="svc-col">
            <div className="svc-head">Auto (ai-bridge)</div>
            <Controls service="ai-bridge" />
          </div>
        </div>
      </Card>

      {/* Fila 1: Estado + Decisiones */}
      <div className="grid2" style={{ marginTop: 12 }}>
        <Card title="Estado">
          <div className="badges">
            <span className={`badge ${slsActive ? "ok" : "fail"}`}>
              sls-bot: {slsActive ? "activo" : "inactivo"}
            </span>
            <span className={`badge ${aiActive ? "ok" : "fail"}`}>
              ai-bridge: {aiActive ? "activo" : "inactivo"}
            </span>
          </div>

          <div className="kv">
            <div>
              <span>Entorno:</span> {status?.bot?.config?.env ?? "-"}
            </div>
            <div>
              <span>Exchange:</span> Bybit
            </div>
            <div>
              <span>Base URL:</span> {status?.bot?.config?.bybit?.base_url ?? "-"}
            </div>
            <div>
              <span>Simbolos:</span> {(status?.bot?.config?.bybit?.symbols || []).join(", ")}
            </div>
          </div>

          <div className="kv muted">
            <div>
              <span>Health UTC:</span> {status?.bot?.api_health?.time ?? "-"}
            </div>
            <div>
              <span>PID API:</span> {status?.bot?.api_health?.pid ?? "-"}
            </div>
          </div>

          {riskDetails ? (
            <div className="risk-block">
              <div className="badges" style={{ marginBottom: 4 }}>
                <span className="badge">
                  Racha pérdidas: {riskDetails.consecutive_losses ?? 0}
                </span>
                {riskDetails.active_cooldown_reason ? (
                  <span className="badge warn">
                    Cooldown ({riskDetails.active_cooldown_reason}) · {formatDuration(cooldownSeconds)}
                  </span>
                ) : (
                  <span className="badge ok">Operando</span>
                )}
              </div>
              {riskDetails.recent_results?.length ? (
                <ul className="risk-results">
                  {riskDetails.recent_results.slice(-5).map((res, idx) => (
                    <li key={idx} className={res.pnl && res.pnl < 0 ? "neg" : "pos"}>
                      {res.pnl?.toFixed(2)} USDT
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty small">Sin historial reciente</div>
              )}
            </div>
          ) : null}
        </Card>

        <Card title="Cerebro IA">
          {cerebro?.enabled ? (
            <>
              <div className="kv">
                <div>
                  <span>Última iteración:</span> {cerebro?.time ?? "-"}
                </div>
                <div>
                  <span>Experiencias:</span> {cerebro?.memory?.total ?? 0} ({Math.round((cerebro?.memory?.win_rate ?? 0) * 100)}% win)
                </div>
              </div>
              <div className="cerebro-controls">
                <label>
                  Símbolo
                  <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
                    {availableSymbols.length === 0 ? <option value="ALL">-</option> : null}
                    {availableSymbols.map((sym) => (
                      <option key={sym} value={sym}>
                        {sym}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Timeframe
                  <select value={timeframeFilter} onChange={(e) => setTimeframeFilter(e.target.value)}>
                    {availableTimeframes.length === 0 ? <option value="ALL">-</option> : null}
                    {availableTimeframes.map((tf) => (
                      <option key={tf} value={tf}>
                        {tf}
                      </option>
                    ))}
                  </select>
                </label>
                <button onClick={forceDecision} disabled={forceStatus.state === "loading"}>
                  {forceStatus.state === "loading" ? "Forzando..." : "Forzar decisión"}
                </button>
              </div>
              {forceStatus.message ? (
                <div className={`cerebro-force-msg ${forceStatus.state}`}>{forceStatus.message}</div>
              ) : null}
              <div className="cerebro-chart">
                {filteredHistory.length ? (
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none">
                    <polyline points={chartPoints} />
                  </svg>
                  ) : (
                  <div className="empty small">Sin historial de confianza</div>
                )}
              </div>
              {riskDetails.dynamic_risk?.enabled ? (
                <div className="risk-dynamic">
                  Multiplicador dinámico: x{Number(riskDetails.dynamic_risk.multiplier ?? 1).toFixed(2)} · Equity {formatEquity(riskDetails.dynamic_risk.current_equity)} /{" "}
                  {formatEquity(riskDetails.dynamic_risk.start_equity)}
                </div>
              ) : (
                <div className="risk-dynamic muted">Riesgo dinámico inactivo</div>
              )}
              {cerebro?.decisions && Object.keys(cerebro.decisions).length ? (
                <ul className="cerebro-decisions">
                  {filteredEntries.map(([key, dec]) => {
                    const meta = dec.metadata || {};
                    const sessionGuard = meta.session_guard || undefined;
                    const guardLabel = describeSessionGuard(sessionGuard);
                    const sentimentBadge = classifySentiment(meta.news_sentiment);
                    const newsMeta = meta.news || undefined;
                    const newsAge = formatNewsAge(newsMeta?.latest_ts);
                    return (
                      <li key={key}>
                        <div className="cerebro-head">
                          <strong>{key}</strong>
                          <span className={`badge ${dec.action === "NO_TRADE" ? "warn" : dec.action === "LONG" ? "ok" : "fail"}`}>
                            {dec.action}
                          </span>
                        </div>
                        <div className="cerebro-meta">
                          Confianza {Math.round((dec.confidence ?? 0) * 100)}% &middot; Riesgo {dec.risk_pct?.toFixed(2)}% &middot; Lev {dec.leverage}
                        </div>
                        {(guardLabel || sentimentBadge) && (
                          <div className="cerebro-tags">
                            {guardLabel && (
                              <span className={`badge badge-mini ${sessionGuard?.block_trade ? "fail" : "warn"}`} title={sessionGuard?.reason ?? ""}>
                                {guardLabel}
                              </span>
                            )}
                            {sentimentBadge && (
                              <span className={`badge badge-mini ${sentimentBadge.className}`} title={newsMeta?.latest_title ?? ""}>
                                {sentimentBadge.label}
                                {newsMeta?.is_fresh === false ? " &middot; vieja" : ""}
                              </span>
                            )}
                          </div>
                        )}
                        {sessionGuard?.should_close_positions ? (
                          <div className="cerebro-alert">Recomendaci&oacute;n: cerrar o reducir posiciones antes de la apertura.</div>
                        ) : null}
                        {newsMeta?.latest_title ? (
                          <div className="cerebro-news">
                            {newsMeta.latest_url ? (
                              <a href={newsMeta.latest_url} target="_blank" rel="noreferrer">
                                {newsMeta.latest_title}
                              </a>
                            ) : (
                              newsMeta.latest_title
                            )}
                            {newsAge ? ` &middot; ${newsAge}` : null}
                          </div>
                        ) : null}
                        <div className="cerebro-summary">{dec.summary}</div>
                        {dec.reasons?.length ? (
                          <ul className="cerebro-reasons">
                            {dec.reasons.map((reason, idx) => (
                              <li key={`${key}-reason-${idx}`}>{reason}</li>
                            ))}
                          </ul>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="empty small">Sin decisiones recientes</div>
              )}
            </>
          ) : (
            <div className="empty small">Cerebro deshabilitado</div>
          )}
        </Card>

        <Card title="Decisiones (ultimas)">
          {decisiones?.length ? (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Hora (UTC)</th>
                    <th>Simbolo</th>
                    <th>Lado</th>
                    <th className="right">Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {decisiones.map((r, i) => (
                    <tr key={`${r.ts ?? i}-${i}`}>
                      <td>{r.ts ?? "-"}</td>
                      <td>{r.symbol ?? "-"}</td>
                      <td>{r.side ?? "-"}</td>
                      <td className="right">
                        {typeof r.confidence === "number" ? r.confidence.toFixed(2) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">Sin datos</div>
          )}
        </Card>
      </div>

      {/* Fila 2: Logs + PnL */}
      <div className="grid2" style={{ marginTop: 12 }}>
        <Card title="Logs del bridge (ultimas)">
          {logs?.length ? (
            <ul className="loglist mono scroll">
              {logs.map((ln, i) => (
                <li key={i}>{ln.trim()}</li>
              ))}
            </ul>
          ) : (
            <div className="empty">Sin datos</div>
          )}
        </Card>

        <Card title="PnL diario (7 dias)">
          {pnl?.length ? (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Dia</th>
                    <th className="right">PnL (EUR)</th>
                  </tr>
                </thead>
                <tbody>
                  {pnl.map((item) => (
                    <React.Fragment key={item.day}>
                      <tr>
                        <td>
                          <div className="pnl-day">
                            <span>{item.day}</span>
                            <span className={`badge badge-mini ${item.from_fills ? "ok" : "muted"}`}>
                              {item.from_fills ? "fills" : "log"}
                            </span>
                          </div>
                        </td>
                        <td className={`right ${item.pnl_eur >= 0 ? "pos" : "neg"}`}>{item.pnl_eur.toFixed(2)}</td>
                      </tr>
                      {item.symbols && item.symbols.length ? (
                        <tr className="pnl-symbol-row">
                          <td colSpan={2}>
                            <ul className="pnl-symbols">
                              {item.symbols.map((sym) => (
                                <li key={`${item.day}-${sym.symbol}`}>
                                  <div className="pnl-symbol-head">
                                    <span className="mono">{sym.symbol}</span>
                                    <span className={`pnl-symbol-pnl ${sym.pnl_eur >= 0 ? "pos" : "neg"}`}>
                                      {sym.pnl_eur.toFixed(2)}
                                    </span>
                                  </div>
                                  <div className="pnl-symbol-meta">
                                    <span>{sym.trades ?? 0} trades</span>
                                    <span>fees {(sym.fees_eur ?? 0).toFixed(2)}</span>
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      ) : null}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">Sin datos</div>
          )}
        </Card>
      </div>
    </>
  );
}

