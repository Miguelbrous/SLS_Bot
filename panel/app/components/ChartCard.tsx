"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
export type ChartPayload = { candles: ChartCandle[]; trades: ChartTrade[] };

type Props = {
  data: ChartPayload | null;
  loading: boolean;
  symbol: string;
  timeframe: string;
  symbols: string[];
  timeframes: string[];
  onSymbolChange: (value: string) => void;
  onTimeframeChange: (value: string) => void;
};

export default function ChartCard({
  data,
  loading,
  symbol,
  timeframe,
  symbols,
  timeframes,
  onSymbolChange,
  onTimeframeChange,
}: Props) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasData = Boolean(data && data.candles?.length);
  const normalizedTrades = useMemo(() => {
    if (!data?.trades?.length) return [];
    return data.trades.map((trade) => ({
      ...trade,
      time: normalizeTime(trade.time),
    }));
  }, [data?.trades]);
  const symbolOptions = useMemo(() => symbols, [symbols]);
  const timeframeOptions = useMemo(() => timeframes, [timeframes]);

  useEffect(() => {
    setError(null);
    if (!hasData || !chartRef.current) return;
    let disposed = false;
    let chartApi: any = null;
    let cleanup: (() => void) | null = null;

    (async () => {
      try {
        const { createChart } = await import("lightweight-charts");
        if (disposed || !chartRef.current) {
          return;
        }
        const node = chartRef.current;
        chartApi = createChart(node, {
          layout: { background: { color: "#0b0b0b" }, textColor: "#f2f2f2" },
          grid: { vertLines: { color: "#1f1f1f" }, horzLines: { color: "#1f1f1f" } },
          crosshair: { mode: 0 },
          timeScale: { timeVisible: true, secondsVisible: false },
        });
        const candleSeries = chartApi.addCandlestickSeries({
          upColor: "#00e0a6",
          downColor: "#ff6b6b",
          borderVisible: false,
          wickUpColor: "#00e0a6",
          wickDownColor: "#ff6b6b",
        });
        candleSeries.setData(data!.candles.map(normalizeCandle));
        if (normalizedTrades.length) {
          candleSeries.setMarkers(
            normalizedTrades.map((trade) => ({
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
            }))
          );
        }
        const resize = () => {
          if (!chartApi || !chartRef.current) return;
          const rect = chartRef.current.getBoundingClientRect();
          chartApi.applyOptions({ width: Math.max(0, rect.width), height: Math.max(220, rect.height) });
        };
        resize();
        window.addEventListener("resize", resize);
        const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
        observer?.observe(node);
        chartApi.timeScale().fitContent();

        cleanup = () => {
          window.removeEventListener("resize", resize);
          observer?.disconnect();
        };
      } catch (err) {
        console.error("[ChartCard] Error creando el chart", err);
        setError("No se pudo renderizar el gráfico (lightweight-charts no disponible).");
      }
    })();

    return () => {
      disposed = true;
      cleanup?.();
      if (chartApi) {
        chartApi.remove();
      }
    };
  }, [data, hasData, normalizedTrades]);

  const latestTs = useMemo(() => {
    if (!data?.candles?.length) return null;
    const last = data.candles[data.candles.length - 1];
    const ms = normalizeTime(last.time) * 1000;
    return new Date(ms);
  }, [data?.candles]);

  return (
    <div className="card chart-card">
      <div className="dashboard-title">
        <h2>
          Serie principal – {symbol} {timeframe}
        </h2>
        {latestTs ? <span className="badge muted">Última vela {latestTs.toLocaleString()}</span> : null}
        {loading ? <span className="badge muted">Cargando chart…</span> : null}
      </div>
      <div className="toolbar">
        <label>
          Símbolo
          <select value={symbol} onChange={(e) => onSymbolChange(e.target.value)}>
            {symbolOptions.map((sym) => (
              <option key={sym} value={sym}>
                {sym}
              </option>
            ))}
          </select>
        </label>
        <label>
          Timeframe
          <select value={timeframe} onChange={(e) => onTimeframeChange(e.target.value)}>
            {timeframeOptions.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div ref={chartRef} className="chart-container">
        {error ? <div className="empty small">{error}</div> : null}
        {!hasData && !loading && !error ? <div className="empty small">Sin datos disponibles</div> : null}
      </div>
    </div>
  );
}

function normalizeTime(value: number): number {
  if (!value) return 0;
  return value > 10_000_000_000 ? Math.floor(value / 1000) : Math.floor(value);
}

function normalizeCandle(candle: ChartCandle): ChartCandle {
  return {
    ...candle,
    time: normalizeTime(candle.time),
  };
}
