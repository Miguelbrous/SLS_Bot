"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import type { ChartPayload } from "../components/ChartCard";
import Sparkline from "../components/Sparkline";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8880";
const PANEL_TOKEN = process.env.NEXT_PUBLIC_PANEL_API_TOKEN?.trim();
const GRAFANA_BASE_URL = process.env.NEXT_PUBLIC_GRAFANA_BASE_URL?.replace(/\/$/, "");
const GRAFANA_ARENA_UID = process.env.NEXT_PUBLIC_GRAFANA_ARENA_UID?.trim();
const GRAFANA_BOT_UID = process.env.NEXT_PUBLIC_GRAFANA_BOT_UID?.trim();
const PROM_BASE_URL = process.env.NEXT_PUBLIC_PROMETHEUS_BASE_URL?.replace(/\/$/, "");

type SummaryMetric = { name: string; value?: number | null; formatted?: string | null; delta?: number | null; delta_formatted?: string | null };
type SummaryIssue = { severity: "info" | "warning" | "error"; message: string };
type SummaryAlert = { name: string; count: number; severity: string; hint: string; latest?: string | null };
type SummaryTrade = {
  ts: string;
  symbol: string;
  timeframe?: string | null;
  side?: string | null;
  pnl?: number | null;
  confidence?: number | null;
  risk_pct?: number | null;
  reason?: string | null;
};
type DashboardSummary = {
  level: "ok" | "warning" | "error";
  summary: string;
  mode?: string | null;
  updated_at: string;
  metrics: SummaryMetric[];
  issues: SummaryIssue[];
  alerts: SummaryAlert[];
  recent_trades: SummaryTrade[];
  recent_pnl: SummaryTrade[];
};

type ArenaRankingEntry = {
  id: string;
  name: string;
  category: string;
  mode: string;
  engine: string;
  score: number;
  balance?: number | null;
  goal?: number | null;
  wins?: number | null;
  losses?: number | null;
  drawdown_pct?: number | null;
};
type ArenaRankingResponse = { count: number; ranking: ArenaRankingEntry[] };
type ArenaState = { current_goal?: number | null; goal_increment?: number | null; wins?: number | null };
type ObservabilitySummary = {
  timestamp: string;
  arena: {
    current_goal?: number | null;
    wins?: number | null;
    ticks_since_win?: number | null;
    last_tick_ts?: string | null;
    tick_age_seconds?: number | null;
  };
  bot: { drawdown_pct?: number | null };
  cerebro: { decisions_per_min?: number | null };
};

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];
const TIMEFRAMES = ["5m", "15m", "1h"];

const ChartCard = dynamic(() => import("../components/ChartCard"), {
  ssr: false,
  loading: () => (
    <div className="card chart-card">
      <p className="muted">Preparando gráfico…</p>
    </div>
  ),
});

const describeAge = (iso?: string | null): string | null => {
  if (!iso) return null;
  try {
    const updated = new Date(iso);
    const diff = (Date.now() - updated.getTime()) / 1000;
    if (diff < 60) return "hace instantes";
    if (diff < 3600) return `hace ${Math.floor(diff / 60)} minutos`;
    return `hace ${Math.floor(diff / 3600)} horas`;
  } catch {
    return null;
  }
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [chartData, setChartData] = useState<ChartPayload | null>(null);
  const [symbol, setSymbol] = useState<string>("BTCUSDT");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [loadingSummary, setLoadingSummary] = useState<boolean>(false);
  const [loadingChart, setLoadingChart] = useState<boolean>(false);
  const [arenaRanking, setArenaRanking] = useState<ArenaRankingEntry[]>([]);
  const [arenaState, setArenaState] = useState<ArenaState | null>(null);
  const [observability, setObservability] = useState<ObservabilitySummary | null>(null);
  const [loadingObservability, setLoadingObservability] = useState<boolean>(false);
  const [loadingArena, setLoadingArena] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [promDrawdown, setPromDrawdown] = useState<Array<{ time: number; value: number }>>([]);
  const [promDecisions, setPromDecisions] = useState<Array<{ time: number; value: number }>>([]);

  const headers = useMemo(() => {
    const h: Record<string, string> = {};
    if (PANEL_TOKEN) h["X-Panel-Token"] = PANEL_TOKEN;
    return h;
  }, []);

  const fetchJSON = useCallback(async <T,>(path: string): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`, { headers });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(body || resp.statusText);
    }
    return resp.json();
  }, [headers]);

  const loadSummary = useCallback(async () => {
    try {
      setLoadingSummary(true);
      const payload = await fetchJSON<DashboardSummary>("/dashboard/summary");
      setSummary(payload);
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando resumen";
      setError(message);
    } finally {
      setLoadingSummary(false);
    }
  }, [fetchJSON]);

  const loadChart = useCallback(async (activeSymbol: string, activeTimeframe: string) => {
    try {
      setLoadingChart(true);
      const payload = await fetchJSON<ChartPayload>(
        `/dashboard/chart?symbol=${encodeURIComponent(activeSymbol)}&timeframe=${encodeURIComponent(activeTimeframe)}`
      );
      setChartData(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando gráfico";
      setError(message);
    } finally {
      setLoadingChart(false);
    }
  }, [fetchJSON]);

  const loadArena = useCallback(async () => {
    try {
      setLoadingArena(true);
      const [rankingPayload, statePayload] = await Promise.all([
        fetchJSON<ArenaRankingResponse>("/arena/ranking"),
        fetchJSON<ArenaState>("/arena/state"),
      ]);
      setArenaRanking((rankingPayload.ranking || []).slice(0, 10));
      setArenaState(statePayload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando arena";
      setError(message);
    } finally {
      setLoadingArena(false);
    }
  }, [fetchJSON]);

  const loadObservability = useCallback(async () => {
    try {
      setLoadingObservability(true);
      const payload = await fetchJSON<ObservabilitySummary>("/observability/summary");
      setObservability(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando observabilidad";
      setError(message);
    } finally {
      setLoadingObservability(false);
    }
  }, [fetchJSON]);

  const loadPrometheusSeries = useCallback(
    async (metric: string, setter: (points: Array<{ time: number; value: number }>) => void) => {
      if (!PROM_BASE_URL) return;
      try {
        const end = Math.floor(Date.now() / 1000);
        const start = end - 3600;
        const resp = await fetch(
          `${PROM_BASE_URL}/api/v1/query_range?query=${encodeURIComponent(metric)}&start=${start}&end=${end}&step=60`
        );
        if (!resp.ok) return;
        const payload = await resp.json();
        const values = payload.data?.result?.[0]?.values || [];
        const points = values.map((row: [number, string]) => ({ time: row[0], value: parseFloat(row[1]) }));
        setter(points);
      } catch (err) {
        console.debug("Prometheus fetch failed", err);
      }
    },
    []
  );

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadChart(symbol, timeframe);
  }, [symbol, timeframe, loadChart]);

  useEffect(() => {
    loadArena();
  }, [loadArena]);

  useEffect(() => {
    loadObservability();
    const interval = setInterval(loadObservability, 60000);
    return () => clearInterval(interval);
  }, [loadObservability]);

  useEffect(() => {
    if (!PROM_BASE_URL) return;
    loadPrometheusSeries("sls_bot_drawdown_pct", setPromDrawdown);
    loadPrometheusSeries("sls_cerebro_decisions_per_min", setPromDecisions);
    const interval = setInterval(() => {
      loadPrometheusSeries("sls_bot_drawdown_pct", setPromDrawdown);
      loadPrometheusSeries("sls_cerebro_decisions_per_min", setPromDecisions);
    }, 60000);
    return () => clearInterval(interval);
  }, [loadPrometheusSeries]);

  const formattedIssues = summary?.issues ?? [];
  const formattedAlerts = summary?.alerts ?? [];

  const statusClass = summary ? `status-pill ${summary.level}` : "status-pill ok";
  const updatedAgo = useMemo(() => describeAge(summary?.updated_at), [summary?.updated_at]);
  const observabilityAgo = useMemo(() => describeAge(observability?.timestamp), [observability?.timestamp]);
  const grafanaLinks = useMemo(() => {
    if (!GRAFANA_BASE_URL) {
      return [];
    }
    const links: { label: string; href: string }[] = [];
    if (GRAFANA_ARENA_UID) {
      links.push({ label: "Grafana Arena", href: `${GRAFANA_BASE_URL}/d/${GRAFANA_ARENA_UID}` });
    }
    if (GRAFANA_BOT_UID) {
      links.push({ label: "Grafana Bot + Cerebro", href: `${GRAFANA_BASE_URL}/d/${GRAFANA_BOT_UID}` });
    }
    return links;
  }, []);

  const observabilityIssues = useMemo(() => {
    if (!observability) return [] as SummaryIssue[];
    const issues: SummaryIssue[] = [];
    const arena = observability.arena || {};
    const bot = observability.bot || {};
    const cerebro = observability.cerebro || {};
    if ((arena.tick_age_seconds || 0) > 600) {
      issues.push({ severity: "warning", message: "La arena no recibe ticks hace >10 minutos" });
    }
    if ((arena.ticks_since_win || 0) > 20) {
      issues.push({ severity: "warning", message: "Más de 20 ticks sin campeón en la arena" });
    }
    if ((bot.drawdown_pct || 0) > 4) {
      issues.push({ severity: "error", message: `Drawdown del bot ${bot.drawdown_pct?.toFixed(2)}% supera 4%` });
    }
    if (typeof cerebro.decisions_per_min === "number" && cerebro.decisions_per_min < 0.3) {
      issues.push({ severity: "warning", message: "Cerebro genera <0.3 decisiones/min (posible inactividad)" });
    }
    return issues;
  }, [observability]);

  const renderArenaRanking = () => {
    if (loadingArena) return <p>Cargando arena...</p>;
    if (!arenaRanking.length) return <p>No hay datos de la arena todavía.</p>;
    return (
      <div className="arena-table-wrapper">
        <table className="arena-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Estrategia</th>
              <th>Cat.</th>
              <th>Modo</th>
              <th>Balance</th>
              <th>Meta</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {arenaRanking.map((row, idx) => (
              <tr key={row.id}>
                <td>{idx + 1}</td>
                <td>{row.name}</td>
                <td>{row.category}</td>
                <td>{row.mode}</td>
                <td>{typeof row.balance === "number" ? row.balance.toFixed(2) : "-"}</td>
                <td>{typeof row.goal === "number" ? row.goal.toFixed(2) : "-"}</td>
                <td>{row.score.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const formatTickAge = (seconds?: number | null) => {
    if (seconds === undefined || seconds === null) return "N/D";
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins}m ${secs}s`;
    }
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  };

  return (
    <div className="dashboard-page">
      <div className="dashboard-head">
        <div className={statusClass}>
          <span className="status-dot" />
          <div>
            <strong>{summary?.summary ?? "Cargando..."}</strong>
            <p>{summary?.mode ? `Modo ${summary.mode}` : null}</p>
          </div>
        </div>
        <div className="head-meta">
          {updatedAgo ? <span className="badge muted">Actualizado {updatedAgo}</span> : null}
          <Link href="/" className="badge muted">
            ← Volver
          </Link>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="dashboard-section">
        <div className="card">
          <div className="dashboard-title">
            <h2>Observabilidad</h2>
            {loadingObservability ? <span className="badge muted">Actualizando…</span> : null}
            {!loadingObservability && observabilityAgo ? <span className="pill neutral">{observabilityAgo}</span> : null}
            {grafanaLinks.length ? (
              <div className="badges">
                {grafanaLinks.map((link) => (
                  <a key={link.href} href={link.href} target="_blank" rel="noreferrer" className="badge muted">
                    {link.label}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
          {observability ? (
            <div className="metric-grid">
              <div className="metric-card">
                <span>Meta arena</span>
                <strong>
                  {typeof observability.arena.current_goal === "number"
                    ? `€${observability.arena.current_goal.toFixed(2)}`
                    : "—"}
                </strong>
                <small>
                  Victorias {observability.arena.wins ?? 0} · Ticks sin win {observability.arena.ticks_since_win ?? 0}
                </small>
              </div>
              <div className="metric-card">
                <span>Último tick</span>
                <strong>{formatTickAge(observability.arena.tick_age_seconds)}</strong>
                <small>
                  {observability.arena.last_tick_ts
                    ? new Date(observability.arena.last_tick_ts).toLocaleString()
                    : "Sin registro"}
                </small>
              </div>
              <div className="metric-card">
                <span>Drawdown bot</span>
                <strong>
                  {typeof observability.bot.drawdown_pct === "number"
                    ? `${observability.bot.drawdown_pct.toFixed(2)}%`
                    : "—"}
                </strong>
                <small>Estado actual de risk_state.json</small>
              </div>
              <div className="metric-card">
                <span>Decisiones Cerebro</span>
                <strong>
                  {typeof observability.cerebro.decisions_per_min === "number"
                    ? observability.cerebro.decisions_per_min.toFixed(2)
                    : "—"}
                </strong>
                <small>Promedio últimos 15 minutos</small>
              </div>
            </div>
          ) : (
            <div className="empty small">Sin datos de observabilidad.</div>
          )}
          {observabilityIssues.length ? (
            <div className="alert-list" style={{ marginTop: 12 }}>
              {observabilityIssues.map((issue, idx) => (
                <div key={`${issue.message}-${idx}`} className={`alert ${issue.severity}`}>
                  {issue.message}
                </div>
              ))}
            </div>
          ) : null}
          {PROM_BASE_URL ? (
            <div className="sparkline-grid">
              <Sparkline
                data={promDrawdown}
                label="Drawdown última hora"
                color="#ff6b6b"
                valueFormatter={(value) =>
                  typeof value === "number" ? `${value.toFixed(2)}%` : "N/D"
                }
              />
              <Sparkline
                data={promDecisions}
                label="Decisiones/min última hora"
                color="#00e0a6"
                valueFormatter={(value) =>
                  typeof value === "number" ? value.toFixed(2) : "N/D"
                }
              />
            </div>
          ) : null}
        </div>
      </section>

      <section className="dashboard-section">
        <div className="card">
          <div className="dashboard-title">
            <h2>Indicadores</h2>
            {loadingSummary ? <span className="badge muted">Actualizando…</span> : null}
          </div>
          <div className="metric-grid">
            {summary?.metrics.map((metric) => (
              <div key={metric.name} className="metric-card">
                <span>{metric.name}</span>
                <strong>{metric.formatted ?? metric.value?.toFixed(2) ?? "—"}</strong>
                {metric.delta_formatted ? <small>{metric.delta_formatted}</small> : null}
              </div>
            )) ?? <div className="empty small">Sin métricas disponibles</div>}
          </div>
        </div>
      </section>

      <section className="dashboard-section">
        <div className="card">
          <div className="dashboard-title">
            <h2>Arena de estrategias</h2>
            {arenaState?.current_goal ? (
              <span className="pill neutral">
                Meta actual €{arenaState.current_goal?.toFixed(2)} · Victorias acumuladas {arenaState.wins ?? 0}
              </span>
            ) : null}
          </div>
          {renderArenaRanking()}
        </div>
      </section>

      <section className="dashboard-section grid2">
        <div className="card">
          <div className="dashboard-title">
            <h2>Problemas detectados</h2>
          </div>
          {formattedIssues.length ? (
            <ul className="issue-list">
              {formattedIssues.map((issue, idx) => (
                <li key={`${issue.message}-${idx}`} className={issue.severity}>
                  {issue.message}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty">Sin issues reportados.</div>
          )}
        </div>
        <div className="card">
          <div className="dashboard-title">
            <h2>Alertas recientes</h2>
          </div>
          {formattedAlerts.length ? (
            <ul className="alert-list">
              {formattedAlerts.map((alert) => (
                <li key={alert.name}>
                  <div>
                    <span className={`label severity-${alert.severity}`}>{alert.name}</span>
                    <span className="badge muted">x{alert.count}</span>
                  </div>
                  <div>{alert.hint}</div>
                  {alert.latest ? <small className="muted">Última: {new Date(alert.latest).toLocaleString()}</small> : null}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty">Sin alertas en la ventana analizada.</div>
          )}
        </div>
      </section>

      <section className="dashboard-section">
        <ChartCard
          data={chartData}
          loading={loadingChart}
          symbol={symbol}
          timeframe={timeframe}
          symbols={SYMBOLS}
          timeframes={TIMEFRAMES}
          onSymbolChange={setSymbol}
          onTimeframeChange={setTimeframe}
        />
      </section>

      <section className="dashboard-section grid2">
        <div className="card">
          <div className="dashboard-title">
            <h2>Últimas decisiones del Cerebro</h2>
          </div>
          <div className="dashboard-table">
            <table className="table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Símbolo</th>
                  <th>TF</th>
                  <th>Side</th>
                  <th>Conf.</th>
                  <th>Riesgo %</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {summary?.recent_trades.map((trade) => (
                  <tr key={`${trade.ts}-${trade.symbol}-${trade.timeframe}-${trade.side}`}>
                    <td>{new Date(trade.ts).toLocaleString()}</td>
                    <td>{trade.symbol}</td>
                    <td>{trade.timeframe ?? "-"}</td>
                    <td>{trade.side ?? "-"}</td>
                    <td className="right">
                      {typeof trade.confidence === "number" ? `${(trade.confidence * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="right">
                      {typeof trade.risk_pct === "number" ? `${trade.risk_pct.toFixed(2)}%` : "—"}
                    </td>
                    <td>{trade.reason ?? "—"}</td>
                  </tr>
                )) ?? (
                  <tr>
                    <td colSpan={7} className="empty small">
                      Sin decisiones registradas
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="dashboard-title">
            <h2>PnL reciente</h2>
          </div>
          <div className="dashboard-table">
            <table className="table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Símbolo</th>
                  <th>TF</th>
                  <th className="right">PnL</th>
                </tr>
              </thead>
              <tbody>
                {summary?.recent_pnl.map((trade) => (
                  <tr key={`${trade.ts}-${trade.symbol}-${trade.pnl}`}>
                    <td>{trade.ts ? new Date(trade.ts).toLocaleString() : "-"}</td>
                    <td>{trade.symbol}</td>
                    <td>{trade.timeframe ?? "-"}</td>
                    <td className={`right ${trade.pnl && trade.pnl < 0 ? "neg" : "pos"}`}>
                      {typeof trade.pnl === "number" ? trade.pnl.toFixed(2) : "—"}
                    </td>
                  </tr>
                )) ?? (
                  <tr>
                    <td colSpan={4} className="empty small">
                      Aún no hay operaciones cerradas.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
