"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";

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
  drawdown_pct?: number | null;
  max_drawdown_pct?: number | null;
  sharpe_ratio?: number | null;
  trades?: number | null;
}

interface ArenaState {
  current_goal?: number | null;
  goal_increment?: number | null;
  wins?: number | null;
  last_tick_ts?: string | null;
  ticks_since_win?: number | null;
}

interface LedgerEntry {
  ts: string;
  pnl: number;
  balance_after: number;
  reason?: string | null;
}

interface ArenaNote {
  strategy_id: string;
  note: string;
  author?: string | null;
  ts: string;
}

const ArenaDetail = dynamic(() => import("../components/ArenaDetail"), {
  ssr: false,
  loading: () => <div className="empty">Cargando detalle…</div>,
});

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

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (PANEL_TOKEN) headers["X-Panel-Token"] = PANEL_TOKEN;
  const resp = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: body ? JSON.stringify(body) : undefined });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || resp.statusText);
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
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [notes, setNotes] = useState<ArenaNote[]>([]);
  const [noteMessage, setNoteMessage] = useState("");
  const [noteLoading, setNoteLoading] = useState(false);
  const [minTrades, setMinTrades] = useState(60);
  const [minSharpe, setMinSharpe] = useState(0.35);
  const [maxDrawdown, setMaxDrawdown] = useState(30);
  const [forcePromotion, setForcePromotion] = useState(false);
  const handleLedgerExport = useCallback(
    (entries: LedgerEntry[]) => {
      if (!entries.length) return;
      setActionMessage(`Exportaste ${entries.length} operaciones a CSV.`);
      setTimeout(() => setActionMessage(null), 3500);
    },
    []
  );

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
      const [ledgerResp, notesResp] = await Promise.all([
        fetchJSON<{ entries: LedgerEntry[] }>(`/arena/ledger?strategy_id=${encodeURIComponent(strategyId)}`),
        fetchJSON<{ notes: ArenaNote[] }>(`/arena/notes?strategy_id=${encodeURIComponent(strategyId)}`),
      ]);
      setLedger(ledgerResp.entries || []);
      setNotes(notesResp.notes || []);
      setSelected(strategyId);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error cargando ledger";
      setError(message);
    } finally {
      setLoadingLedger(false);
    }
  };

  const forceTick = async () => {
    try {
      setActionMessage("Ejecutando tick...");
      await postJSON("/arena/tick");
      await loadData();
      setActionMessage("Tick ejecutado correctamente.");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error ejecutando tick";
      setError(message);
    } finally {
      setTimeout(() => setActionMessage(null), 4000);
    }
  };

  const promoteSelected = async () => {
    if (!selected) return;
    try {
      setActionMessage("Generando paquete de promoción...");
      const params = new URLSearchParams({
        strategy_id: selected,
        min_trades: String(minTrades),
        min_sharpe: String(minSharpe),
        max_drawdown: String(maxDrawdown),
      });
      if (forcePromotion) params.set("force", "true");
      await postJSON(`/arena/promote?${params.toString()}`);
      setActionMessage(`Estrategia ${selected} exportada (bot/arena/promoted/${selected}).`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error exportando estrategia";
      setError(message);
    } finally {
      setTimeout(() => setActionMessage(null), 4000);
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

  const handleAddNote = async () => {
    if (!selected || !noteMessage.trim()) return;
    try {
      setNoteLoading(true);
      await postJSON("/arena/notes", {
        strategy_id: selected,
        note: noteMessage.trim(),
        author: "panel",
      });
      setNoteMessage("");
      const notesResp = await fetchJSON<{ notes: ArenaNote[] }>(`/arena/notes?strategy_id=${encodeURIComponent(selected)}`);
      setNotes(notesResp.notes || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error guardando nota";
      setError(message);
    } finally {
      setNoteLoading(false);
    }
  };

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
          <button onClick={forceTick} disabled={loading}>
            Forzar tick
          </button>
          <button onClick={promoteSelected} disabled={!selected}>
            Exportar paquete
          </button>
          <button onClick={loadData} disabled={loading}>
            {loading ? "Actualizando..." : "Refrescar"}
          </button>
        </div>
      </header>

      <div className="toolbar" style={{ marginBottom: 16 }}>
        <label>
          Min trades
          <input type="number" value={minTrades} onChange={(e) => setMinTrades(Number(e.target.value) || 0)} min={10} />
        </label>
        <label>
          Min Sharpe
          <input type="number" step="0.05" value={minSharpe} onChange={(e) => setMinSharpe(Number(e.target.value) || 0)} />
        </label>
        <label>
          Max DD (%)
          <input type="number" value={maxDrawdown} onChange={(e) => setMaxDrawdown(Number(e.target.value) || 0)} min={5} />
        </label>
        <label className="checkbox-inline">
          <input type="checkbox" checked={forcePromotion} onChange={(e) => setForcePromotion(e.target.checked)} /> Forzar exportación
        </label>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {actionMessage ? <div className="badge muted">{actionMessage}</div> : null}

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
                  <th>Sharpe</th>
                  <th>Max DD%</th>
                  <th>Trades</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredRanking.map((row, idx) => (
                  <tr key={row.id} className={selected === row.id ? "active" : undefined}>
                    <td>{idx + 1}</td>
                    <td>{row.name}</td>
                    <td>{row.category}</td>
                    <td>{row.mode}</td>
                    <td>{typeof row.balance === "number" ? row.balance.toFixed(2) : "-"}</td>
                    <td>{typeof row.goal === "number" ? row.goal.toFixed(2) : "-"}</td>
                    <td>{row.score.toFixed(3)}</td>
                    <td>{row.wins ?? 0}</td>
                    <td>{typeof row.sharpe_ratio === "number" ? row.sharpe_ratio.toFixed(2) : "-"}</td>
                    <td>{typeof row.max_drawdown_pct === "number" ? row.max_drawdown_pct.toFixed(1) : "-"}</td>
                    <td>{row.trades ?? "-"}</td>
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
          {selected ? (
            <ArenaDetail
              selection={currentSelection || undefined}
              ledger={ledger}
              notes={notes}
              noteMessage={noteMessage}
              onNoteMessageChange={setNoteMessage}
              onAddNote={handleAddNote}
              loadingLedger={loadingLedger}
              noteLoading={noteLoading}
              onExport={handleLedgerExport}
            />
          ) : (
            <div className="empty">Selecciona una estrategia del ranking para ver su ledger.</div>
          )}
        </div>
      </section>
    </div>
  );
}
