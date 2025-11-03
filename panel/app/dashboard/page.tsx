"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8880";
const PANEL_TOKEN = process.env.NEXT_PUBLIC_PANEL_API_TOKEN?.trim();

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

type ChartCandle = { time: number; open: number; high: number; low: number; close: number };
type ChartTrade = {
  time: number;
  symbol: string;
  timeframe?: string | null;
  side?: string | null;
  reason?: string | null;
  confidence?: number | null;
  risk_pct?: number | null;
};
type ChartPayload = { candles: ChartCandle[]; trades: ChartTrade[] };

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];
const TIMEFRAMES = ["5m", "15m", "1h"];

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [chartData, setChartData] = useState<ChartPayload | null>(null);
  const [symbol, setSymbol] = useState<string>("BTCUSDT");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [loadingSummary, setLoadingSummary] = useState<boolean>(false);
  const [loadingChart, setLoadingChart] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement | null>(null);

  const headers = useMemo(() => {
    const h: Record<string, string> = {};
    if (PANEL_TOKEN) h["X-Panel-Token"] = PANEL_TOKEN;
    return h;
  }, []);

  async function fetchJSON<T>(path: string): Promise<T> {
    const resp = await fetch(`${API_BASE}${path}`, { headers });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(body || resp.statusText);
    }
    return resp.json();
  }

  async function loadSummary() {
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
  }

  async function loadChart(activeSymbol: string, activeTimeframe: string) {
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
  }

  useEffect(() => {
    loadSummary();
  }, []);

  useEffect(() => {
    loadChart(symbol, timeframe);
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!chartData || !chartRef.current) return;
    let chartApi: any = null;
    let candleSeries: any = null;
    let disposed = false;

    (async () => {
      const { createChart } = await import("lightweight-charts");
      if (disposed || !chartRef.current) return;
      const node = chartRef.current;
      chartApi = createChart(node, {
        layout: { background: { color: "#0b0b0b" }, textColor: "#f2f2f2" },
        grid: { vertLines: { color: "#1f1f1f" }, horzLines: { color: "#1f1f1f" } },
        crosshair: { mode: 0 },
        timeScale: { timeVisible: true, secondsVisible: false },
      });
      candleSeries = chartApi.addCandlestickSeries({
        upColor: "#00e0a6",
        downColor: "#ff6b6b",
        borderVisible: false,
        wickUpColor: "#00e0a6",
        wickDownColor: "#ff6b6b",
      });
      candleSeries.setData(chartData.candles);
      if (chartData.trades.length) {
        const markers = chartData.trades.map((trade) => ({
          time: trade.time as any,
          position: trade.side === "SHORT" ? "aboveBar" : "belowBar",
          color: trade.side === "SHORT" ? "#ff6b6b" : "#00e0a6",
          shape: trade.side === "SHORT" ? "arrowDown" : "arrowUp",
          text: trade.side ?? "",
          tooltip: [
            `Símbolo: ${trade.symbol}`,
            trade.timeframe ? `TF: ${trade.timeframe}` : "",
            trade.reason ? `Motivo: ${trade.reason}` : "",
            typeof trade.confidence === "number" ? `Confianza: ${(trade.confidence * 100).toFixed(1)}%` : "",
            typeof trade.risk_pct === "number" ? `Riesgo: ${trade.risk_pct.toFixed(2)}%` : "",
          ]
            .filter(Boolean)
            .join("\n"),
        }));
        candleSeries.setMarkers(markers);
      }
      const resize = () => {
        if (!chartApi || !chartRef.current) return;
        const { clientWidth } = chartRef.current;
        chartApi.applyOptions({ width: clientWidth });
      };
      resize();
      window.addEventListener("resize", resize);
      chartApi.timeScale().fitContent();
      const observer = new ResizeObserver(resize);
      observer.observe(node);
      candleSeries.subscribeCrosshairMove((param: any) => {
        if (!param || !param.time) return;
      });
      chartApi._cleanup = () => {
        window.removeEventListener("resize", resize);
        observer.disconnect();
      };
    })();

    return () => {
      disposed = true;
      if (chartApi) {
        chartApi._cleanup?.();
        chartApi.remove();
      }
    };
  }, [chartData]);

  const formattedIssues = summary?.issues ?? [];
  const formattedAlerts = summary?.alerts ?? [];

  const statusClass = summary ? `status-pill ${summary.level}` : "status-pill ok";
  const updatedAgo = useMemo(() => {
    if (!summary?.updated_at) return null;
    try {
      const updated = new Date(summary.updated_at);
      const diff = (Date.now() - updated.getTime()) / 1000;
      if (diff < 60) return "hace instantes";
      if (diff < 3600) return `hace ${Math.floor(diff / 60)} minutos`;
      return `hace ${Math.floor(diff / 3600)} horas`;
    } catch {
      return null;
    }
  }, [summary?.updated_at]);

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
        <div className="card chart-card">
          <div className="dashboard-title">
            <h2>TradingView (Lightweight) – {symbol} {timeframe}</h2>
            {loadingChart ? <span className="badge muted">Cargando chart…</span> : null}
          </div>
          <div className="toolbar">
            <label>
              Símbolo
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {SYMBOLS.map((sym) => (
                  <option key={sym} value={sym}>
                    {sym}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Timeframe
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div ref={chartRef} className="chart-container" />
        </div>
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
