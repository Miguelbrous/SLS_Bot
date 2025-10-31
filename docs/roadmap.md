# Roadmap SLS_Bot

Documento vivo con los objetivos estratégicos y el estado de ejecución. Última actualización: 2025-10-31.

## Objetivos generales del proyecto

| # | Objetivo | Estado | Comentarios |
|---|----------|--------|-------------|
| 1 | Automatizar validación de `.env` y `config/config.json` multi-modo | ✅ Completo (base) | `scripts/tools/infra_check.py` valida tokens, contraseñas y soporta `--ensure-dirs`. |
| 2 | Normalizar artefactos `logs/{mode}`, `excel/{mode}`, `models/{mode}` con rotación automática | ✅ Completo (base) | `make rotate-artifacts` usa `scripts/tools/rotate_artifacts.py` para archivar logs/modelos por modo. |
| 3 | Integrar healthchecks HTTP y smoke tests en Makefile | ✅ Completo (base) | Nuevos targets `make health` y `make smoke` invocan scripts dedicados. |
| 4 | Orquestar despliegues systemd con reintentos/notificación | 🟡 En curso | `scripts/manage_bot.py` añade `--retries/--retry-delay`; falta integrar notificaciones. |
| 5 | Completar observabilidad (métricas/alertas) | ⭕ Pendiente | Definir stack Prometheus o logs centralizados. |
| 6 | Pipeline CI/CD con linters, tests y build panel | ⭕ Pendiente | Diseñar workflows y artefactos. |
| 7 | Automatizar promoción testnet→real | ⭕ Pendiente | Requiere ampliar `promote_strategy.py` y playbooks. |
| 8 | Endurecer seguridad API (tokens, rate limiting, auditoría) | ⭕ Pendiente | Analizar middlewares, logs y rotación de credenciales. |
| 9 | Garantizar compatibilidad panel/API en cada release | ⭕ Pendiente | Definir control de versiones y contratos DTO. |
| 10 | Playbooks operativos (bootstrap, claves, recuperación) | ⭕ Pendiente | Documentar procedimientos paso a paso. |

## Objetivos Cerebro IA

| # | Objetivo | Estado | Comentarios |
|---|----------|--------|-------------|
| 1 | Desacoplar data sources con colas/caching | ✅ Completo | `DataIngestionManager` encola `IngestionTask` y cachea respuestas con TTL. |
| 2 | Extender FeatureStore con normalización avanzada | ✅ Completo | `FeatureStore` mantiene medias/varianzas y expone slices normalizados. |
| 3 | Evaluación continua de modelos (A/B heurístico vs ML) | ✅ Completo | `EvaluationTracker` persiste métricas en `logs/<mode>/metrics`. |
| 4 | Detección de anomalías previa a decisiones | ✅ Completo | `AnomalyDetector` aplica z-score y fuerza `NO_TRADE` con motivo. |
| 5 | Pipelines de entrenamiento online vs offline | ✅ Completo | `TrainingPipeline` lanza `cerebro.train` y marca datasets para offline. |
| 6 | Gestión de versiones y rollback de modelos | ✅ Completo | `ModelRegistry` registra artefactos, promueve y permite rollback. |
| 7 | Explicabilidad ligera (drivers de decisiones) | ✅ Completo | Metadata expone razón, score ML, anomalía, simulación y umbral dinámico. |
| 8 | Simulador retroactivo antes de promover decisiones | ✅ Completo | `BacktestSimulator` estima PnL promedio sobre la ventana reciente. |
| 9 | Reportes post-sesión (win rate, drawdown evitado) | ✅ Completo | `ReportBuilder` genera `cerebro_daily_report.json` por sesión. |
| 10 | Límites de confianza dinámicos según volatilidad/datos | ✅ Completo | `DynamicConfidenceGate` ajusta el umbral con base en volatilidad/calidad. |

## Fases de implementación

- **Fase 0 – Preparación (Completada)**: Validación automatizada (`infra_check --ensure-dirs`), directorios creados para ambos modos, comandos `make health`/`make smoke` documentados.
- **Fase 1 – Hardening base (En curso)**: Reintentos systemd y rotación listos; faltan notificaciones y alertas centralizadas.
- **Fase 2 – Ciclo de pruebas (Planificada)**: Ejecutar smoke continuo, datasets simulados y panel en modo test.
- **Fase 3 – Cerebro modular (Planificada)**: Refactor de pipelines internos y métricas.
- **Fase 4 – Entrenamiento continuo (Planificada)**: Automatizar reentrenos/promociones.
- **Fase 5 – Go-live testnet (Planificada)**: Orquestar servicios completos en testnet hasta estabilidad.
- **Fase 6 – Promoción a real (Planificada)**: Replicar configuración con claves mainnet y activar monitoreo extendido.
