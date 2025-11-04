"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8880";
const PANEL_TOKEN = process.env.NEXT_PUBLIC_PANEL_API_TOKEN?.trim();

interface RankingRow {
  id: string;
  name: string;
  category: string;
  mode: string;
  engine: string;
  balance?: number | null;
  goal?: number | null;
  score: number;
  wins?: number | null;
  losses?: number | null;
}

interface ArenaState {
  current_goal?: number | null;
  goal_increment?: number | null;
  wins?: number | null;
}

interface LedgerEntry {
  ts: string;
  pnl: number;
  balance_after: number;
  reason?: string | null;
}

async function fetchJSON<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (PANEL_TOKEN) headers["X-Panel-Token"] = PANEL_TOKEN;
  const resp = await fetch(`${API_BASE}${path}`, { headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(body || resp.statusText);
  }
  return resp.json();
}

export default function ArenaPage() {
  const [ranking, setRanking] = useState<RankingRow[]>([]);
  const [state, setState] = useState<ArenaState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  const loadData = async () => {
    try {
      setLoading(true);
      const [rankingResp, stateResp] = await Promise.all([
        fetchJSON<{ ranking: RankingRow[] }>("/arena/ranking"),
        fetchJSON<ArenaState>("/arena/state"),
      ]);
      setRanking(rankingResp.ranking || []);
      setState(stateResp);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando arena";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const loadLedger = async (strategyId: string) => {
    try {
      setLoadingLedger(true);
      const payload = await fetchJSON<{ entries: LedgerEntry[] }>(`/arena/ledger?strategy_id=${encodeURIComponent(strategyId)}`);
      setLedger(payload.entries || []);
      setSelected(strategyId);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando ledger";
      setError(message);
    } finally {
      setLoadingLedger(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredRanking = useMemo(() => {
    if (categoryFilter === "all") return ranking;
    return ranking.filter((row) => row.category === categoryFilter);
  }, [ranking, categoryFilter]);

  const categories = useMemo(() => {
    const unique = new Set(ranking.map((row) => row.category));
    return ["all", ...Array.from(unique)];
  }, [ranking]);

  const currentSelection = useMemo(() => ranking.find((row) => row.id === selected), [ranking, selected]);

  return (
    <div className="dashboard-container">
      <header className="dashboard-head">
        <div>
          <h1>Arena de estrategias</h1>
          <p className="muted">Ranking completo y ledger reciente.</p>
        </div>
        <div className="badges">
          <Link href="/dashboard" className="badge ok">
            Volver al dashboard
          </Link>
          <button onClick={loadData} disabled={loading}>
            {loading ? "Actualizando..." : "Refrescar"}
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="dashboard-section">
        <div className="card">
          <div className="dashboard-title">
            <h2>Ranking global</h2>
            {state?.current_goal ? (
              <span className="pill neutral">Meta actual €{state.current_goal?.toFixed(2)} · Victorias: {state.wins ?? 0}</span>
            ) : null}
          </div>
          <div className="toolbar" style={{ marginBottom: 12 }}>
            <label>
              Categoría
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                {categories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="arena-table-wrapper">
            <table className="arena-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nombre</th>
                  <th>Cat.</th>
                  <th>Modo</th>
                  <th>Balance</th>
                  <th>Meta</th>
                  <th>Score</th>
                  <th>Wins</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredRanking.map((row, idx) => (
                  <tr key={row.id}>
                    <td>{idx + 1}</td>
                    <td>{row.name}</td>
                    <td>{row.category}</td>
                    <td>{row.mode}</td>
                    <td>{typeof row.balance === "number" ? row.balance.toFixed(2) : "-"}</td>
                    <td>{typeof row.goal === "number" ? row.goal.toFixed(2) : "-"}</td>
                    <td>{row.score.toFixed(3)}</td>
                    <td>{row.wins ?? 0}</td>
                    <td>
                      <button onClick={() => loadLedger(row.id)} disabled={loadingLedger && selected === row.id}>
                        Ver ledger
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="dashboard-section">
        <div className="card">
          <div className="dashboard-title">
            <h2>Ledger reciente</h2>
            {currentSelection ? <span className="pill neutral">{currentSelection.name}</span> : null}
          </div>
          {selected && ledger.length ? (
            <div className="arena-table-wrapper">
              <table className="arena-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>PNL</th>
                    <th>Balance</th>
                    <th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.map((entry) => (
                    <tr key={`${entry.ts}-${entry.balance_after}`}>
                      <td>{new Date(entry.ts).toLocaleString()}</td>
                      <td className={entry.pnl >= 0 ? "pos" : "neg"}>{entry.pnl.toFixed(4)}</td>
                      <td>{entry.balance_after.toFixed(4)}</td>
                      <td>{entry.reason ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">Selecciona una estrategia del ranking para ver su ledger.</div>
          )}
        </div>
      </section>
    </div>
  );
}
