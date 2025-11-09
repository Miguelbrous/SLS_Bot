import Card from "./Card";

type DatasetSummary = {
  summary: { total?: number; win_rate?: number; dominant_symbol_share?: number };
  violations?: string[];
};

type CandidateRow = {
  name: string;
  score: number;
  stats: {
    sharpe?: number;
    calmar?: number;
    profit_factor?: number;
    win_rate?: number;
    max_drawdown?: number;
    trades?: number;
    feature_drift?: number;
  };
  source?: string;
};

export type AutopilotSummary = {
  dataset: DatasetSummary;
  arena: { accepted: CandidateRow[]; rejected: { name: string; violations?: string[] }[] };
};

export default function AutopilotSummaryCard({ summary }: { summary: AutopilotSummary | null }) {
  if (!summary) {
    return (
      <Card title="Autopilot 2V">
        <div className="empty small">Sin resumen disponible</div>
      </Card>
    );
  }
  const dataset = summary.dataset;
  const accepted = summary.arena.accepted || [];
  const top = accepted.slice(0, 4);

  return (
    <Card title="Autopilot 2V">
      <div className="autopilot-dataset">
        <div>
          <span>Filas dataset:</span>
          <strong>{dataset.summary.total ?? 0}</strong>
        </div>
        <div>
          <span>Win rate:</span>
          <strong>{((dataset.summary.win_rate ?? 0) * 100).toFixed(1)}%</strong>
        </div>
        <div>
          <span>Símbolo dominante:</span>
          <strong>{((dataset.summary.dominant_symbol_share ?? 0) * 100).toFixed(1)}%</strong>
        </div>
      </div>
      {dataset.violations?.length ? (
        <div className="autopilot-violations">
          Guardas dataset: {dataset.violations.join(", ")}
        </div>
      ) : (
        <div className="autopilot-violations ok">Dataset OK</div>
      )}
      {top.length ? (
        <div className="tablewrap">
          <table className="table autopilot-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Estrategia</th>
                <th className="right">Score</th>
                <th className="right">Sharpe</th>
                <th className="right">Calmar</th>
                <th className="right">PF</th>
                <th className="right">Win%</th>
                <th className="right">DD%</th>
                <th className="right">Drift</th>
              </tr>
            </thead>
            <tbody>
              {top.map((row, idx) => (
                <tr key={row.name}>
                  <td>{idx + 1}</td>
                  <td>{row.name}</td>
                  <td className="right">{row.score.toFixed(2)}</td>
                  <td className="right">{(row.stats.sharpe ?? 0).toFixed(2)}</td>
                  <td className="right">{(row.stats.calmar ?? 0).toFixed(2)}</td>
                  <td className="right">{(row.stats.profit_factor ?? 0).toFixed(2)}</td>
                  <td className="right">{((row.stats.win_rate ?? 0) * 100).toFixed(1)}%</td>
                  <td className="right">{(row.stats.max_drawdown ?? 0).toFixed(2)}</td>
                  <td className="right">{(row.stats.feature_drift ?? 0).toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty small">No hay candidatos aprobados</div>
      )}
      {summary.arena.rejected?.length ? (
        <div className="autopilot-rejected">
          Rechazados:{" "}
          {summary.arena.rejected
            .slice(0, 3)
            .map((r) => `${r.name} (${(r.violations || []).join("; ")})`)
            .join(" · ")}
        </div>
      ) : null}
    </Card>
  );
}
