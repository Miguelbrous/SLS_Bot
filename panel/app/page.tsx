"use client";

import React, { useEffect, useState } from "react";
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
type RiskStateDetails = {
  consecutive_losses?: number;
  cooldown_until_ts?: number;
  active_cooldown_reason?: string | null;
  cooldown_history?: { ts: string; reason: string; minutes: number }[];
  recent_results?: { ts?: number; pnl?: number }[];
};

export default function Page() {
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [decisiones, setDecisiones] = useState<DecisionRow[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [pnl, setPnl] = useState<PnlItem[]>([]);

  async function loadAll() {
    try {
      const init = PANEL_TOKEN ? { headers: { "X-Panel-Token": PANEL_TOKEN } } : undefined;
      const [s, d, l, p] = await Promise.all([
        fetch(`${API_BASE}/status`, init).then((r) => r.json()),
        fetch(`${API_BASE}/decisiones?limit=25`, init).then((r) => r.json()),
        fetch(`${API_BASE}/logs/bridge?limit=200`, init).then((r) => r.json()),
        fetch(`${API_BASE}/pnl/diario?days=7`, init).then((r) => r.json()),
      ]);
      setStatus(s);
      setDecisiones((d as DecisionsResp).rows || []);
      setLogs((l as LogResp).lines || []);
      setPnl(p.days || []);
    } catch {
      // silencioso para no antagonizar la UI
    }
  }

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 5000);
    return () => clearInterval(id);
  }, []);

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

