"use client";

import React, { useMemo, useState } from "react";

type RankingRow = {
  id: string;
  name: string;
  sharpe_ratio?: number | null;
  max_drawdown_pct?: number | null;
  trades?: number | null;
  wins?: number | null;
  losses?: number | null;
  score: number;
};

type LedgerEntry = {
  ts: string;
  pnl: number;
  balance_after: number;
  reason?: string | null;
};

type ArenaNote = {
  strategy_id: string;
  note: string;
  author?: string | null;
  ts: string;
};

type Props = {
  selection?: RankingRow;
  ledger: LedgerEntry[];
  notes: ArenaNote[];
  noteMessage: string;
  onNoteMessageChange: (value: string) => void;
  onAddNote: () => void;
  loadingLedger: boolean;
  noteLoading: boolean;
  onExport?: (entries: LedgerEntry[]) => void;
};

export default function ArenaDetail({
  selection,
  ledger,
  notes,
  noteMessage,
  onNoteMessageChange,
  onAddNote,
  loadingLedger,
  noteLoading,
  onExport,
}: Props) {
  const [ledgerFilter, setLedgerFilter] = useState<"all" | "wins" | "losses">("all");
  const [noteSearch, setNoteSearch] = useState("");
  const aggregates = useMemo(() => {
    const totalPnl = ledger.reduce((acc, row) => acc + row.pnl, 0);
    const avgPnl = ledger.length ? totalPnl / ledger.length : 0;
    const wins = ledger.filter((row) => row.pnl > 0).length;
    const winRate = ledger.length ? (wins / ledger.length) * 100 : 0;
    const losses = ledger.length - wins;
    return {
      totalPnl,
      avgPnl,
      winRate,
      wins,
      losses,
    };
  }, [ledger]);
  const filteredLedger = useMemo(() => {
    if (ledgerFilter === "wins") return ledger.filter((entry) => entry.pnl > 0);
    if (ledgerFilter === "losses") return ledger.filter((entry) => entry.pnl <= 0);
    return ledger;
  }, [ledger, ledgerFilter]);
  const filteredNotes = useMemo(() => {
    if (!noteSearch.trim()) return notes;
    const term = noteSearch.trim().toLowerCase();
    return notes.filter((note) => note.note.toLowerCase().includes(term) || (note.author || "").toLowerCase().includes(term));
  }, [notes, noteSearch]);
  const isExportEnabled = typeof onExport === "function" && ledger.length > 0;
  const exportCsv = () => {
    if (!isExportEnabled) return;
    const header = "ts,pnl,balance_after,reason\n";
    const rows = ledger
      .map((entry) =>
        [entry.ts, entry.pnl.toFixed(6), entry.balance_after.toFixed(6), JSON.stringify(entry.reason ?? "-")].join(",")
      )
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selection?.id || "arena-ledger"}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    onExport?.(ledger);
  };

  if (loadingLedger) {
    return <div className="empty small">Cargando ledger…</div>;
  }
  if (!selection) {
    return <div className="empty">Selecciona una estrategia del ranking para ver su ledger.</div>;
  }
  if (!ledger.length) {
    return <div className="empty">Sin operaciones registradas en esta estrategia.</div>;
  }

  return (
    <div className="arena-details">
      <div>
        <div className="badges" style={{ marginBottom: 12, flexWrap: "wrap" }}>
          <span className="badge muted">Balance final {ledger[ledger.length - 1].balance_after.toFixed(4)}</span>
          <span className="badge muted">PnL acumulado {aggregates.totalPnl.toFixed(4)}</span>
          <span className="badge muted">Promedio trade {aggregates.avgPnl.toFixed(4)}</span>
          <span className="badge muted">Win rate {aggregates.winRate.toFixed(1)}% ({aggregates.wins}/{aggregates.losses})</span>
          <div className="ledger-filter">
            <button type="button" className={ledgerFilter === "all" ? "badge ok" : "badge muted"} onClick={() => setLedgerFilter("all")}>
              Todos
            </button>
            <button type="button" className={ledgerFilter === "wins" ? "badge ok" : "badge muted"} onClick={() => setLedgerFilter("wins")}>
              Ganadoras
            </button>
            <button type="button" className={ledgerFilter === "losses" ? "badge ok" : "badge muted"} onClick={() => setLedgerFilter("losses")}>
              Perdedoras
            </button>
          </div>
          <button type="button" onClick={exportCsv} disabled={!isExportEnabled}>
            Exportar CSV
          </button>
        </div>
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
              {filteredLedger.map((entry) => (
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
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <div className="metric-card">
            <span>Sharpe</span>
            <strong>{typeof selection.sharpe_ratio === "number" ? selection.sharpe_ratio.toFixed(2) : "-"}</strong>
            <small>Mayor es mejor</small>
          </div>
          <div className="metric-card">
            <span>Max DD %</span>
            <strong>{typeof selection.max_drawdown_pct === "number" ? selection.max_drawdown_pct.toFixed(1) : "-"}</strong>
            <small>Último ciclo</small>
          </div>
          <div className="metric-card">
            <span>Trades</span>
            <strong>{selection.trades ?? "-"}</strong>
            <small>
              Wins/Losses {selection.wins ?? 0}/{selection.losses ?? 0}
            </small>
          </div>
          <div className="metric-card">
            <span>Score</span>
            <strong>{selection.score.toFixed(3)}</strong>
            <small>Balance vs meta</small>
          </div>
        </div>
      </div>
      <div className="notes-card">
        <h3>Notas</h3>
        <input
          type="search"
          value={noteSearch}
          onChange={(e) => setNoteSearch(e.target.value)}
          placeholder="Filtrar notas"
          className="note-search"
        />
        {filteredNotes.length ? (
          <ul className="note-list">
            {filteredNotes.map((note) => (
              <li key={`${note.ts}-${note.note}`}>
                <div>
                  <span>{note.note}</span>
                </div>
                <small>
                  {new Date(note.ts).toLocaleString()} · {note.author || "anon"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty small">Sin notas aún.</div>
        )}
        <div className="note-form">
          <textarea
            value={noteMessage}
            onChange={(e) => onNoteMessageChange(e.target.value)}
            placeholder="Agregar nota (ej. ajustes pendientes, riesgos, etc.)"
          />
          <button onClick={onAddNote} disabled={!noteMessage.trim() || noteLoading}>
            {noteLoading ? "Guardando..." : "Guardar nota"}
          </button>
        </div>
      </div>
    </div>
  );
}
