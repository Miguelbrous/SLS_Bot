# Go/No-Go Report

_Generado: 2025-11-11T15:44:57.590852Z_

## Checklist
- ✅ sls-bot: active
- ✅ sls-api: active
- ✅ sls-cerebro: active
- Failover report: ⚠️ no reportado
- Dataset violaciones: min_rows(4<150)
- Arena candidatos: 1 aceptados / 1 rechazados

## Dataset
- Filas: 4  · Win rate: 75.0%
- Símbolo dominante: 50.0%
- **Violaciones:** min_rows(4<150)

## Top estrategias
| Rank | Estrategia | Score | Sharpe | Calmar | PF | Win% | DD% | Drift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | strategy_alpha | 1.27 | 1.78 | 428.57 | 2.33 | 60.0% | 3.50% | 0.080 |

### Rechazados
- strategy_beta: max_drawdown(6.50>5.00), feature_drift(0.250>0.200)

## Riesgo actual
- Consecutive losses: 3
- Cooldown activo: loss_streak hasta 2025-11-09T20:41:43Z
- Resultados recientes: -2.0, 1.0

## Auditoría (últimos eventos)
- 2025-11-09T20:31:43.972322Z: nginx → sls-bot.status (ok)
- 2025-11-09T20:31:43.976050Z: tester → sls-bot.status (ok)
- 2025-11-11T13:59:22.648168+00:00: tester → sls-bot.status (ok)

## Estado: 🟡 Pendiente