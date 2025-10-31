# Roadmap SLS_Bot

Documento vivo con los objetivos estratégicos y el estado de ejecución. Última actualización: 2025-10-31.

## Objetivos generales del proyecto

| # | Objetivo | Estado | Comentarios |
|---|----------|--------|-------------|
| 1 | Automatizar validación de `.env` y `config/config.json` multi-modo | ✅ Completo (base) | `scripts/tools/infra_check.py` valida tokens, contraseñas y soporta `--ensure-dirs`. |
| 2 | Normalizar artefactos `logs/{mode}`, `excel/{mode}`, `models/{mode}` con rotación automática | 🟡 En curso | Directorios creados via `infra_check --ensure-dirs`; falta automatizar rotación y archivado. |
| 3 | Integrar healthchecks HTTP y smoke tests en Makefile | ✅ Completo (base) | Nuevos targets `make health` y `make smoke` invocan scripts dedicados. |
| 4 | Orquestar despliegues systemd con reintentos/notificación | ⭕ Pendiente | Requiere ajustar `scripts/manage_bot.py` y unidades systemd. |
| 5 | Completar observabilidad (métricas/alertas) | ⭕ Pendiente | Definir stack Prometheus o logs centralizados. |
| 6 | Pipeline CI/CD con linters, tests y build panel | ⭕ Pendiente | Diseñar workflows y artefactos. |
| 7 | Automatizar promoción testnet→real | ⭕ Pendiente | Requiere ampliar `promote_strategy.py` y playbooks. |
| 8 | Endurecer seguridad API (tokens, rate limiting, auditoría) | ⭕ Pendiente | Analizar middlewares, logs y rotación de credenciales. |
| 9 | Garantizar compatibilidad panel/API en cada release | ⭕ Pendiente | Definir control de versiones y contratos DTO. |
| 10 | Playbooks operativos (bootstrap, claves, recuperación) | ⭕ Pendiente | Documentar procedimientos paso a paso. |

## Objetivos Cerebro IA

| # | Objetivo | Estado | Comentarios |
|---|----------|--------|-------------|
| 1 | Desacoplar data sources con colas/caching | ⭕ Pendiente | Requiere rediseñar `DataSources` y scheduling. |
| 2 | Extender FeatureStore con normalización avanzada | ⭕ Pendiente | Necesita análisis de datasets y métricas. |
| 3 | Evaluación continua de modelos (A/B heurístico vs ML) | ⭕ Pendiente | Faltan métricas automáticas y scheduler. |
| 4 | Detección de anomalías previa a decisiones | ⭕ Pendiente | Integrar filtros o modelos adicionales. |
| 5 | Pipelines de entrenamiento online vs offline | ⭕ Pendiente | Definir colas y frecuencias de reentrenos. |
| 6 | Gestión de versiones y rollback de modelos | ⭕ Pendiente | Diseñar metadata + comandos de promoción. |
| 7 | Explicabilidad ligera (drivers de decisiones) | ⭕ Pendiente | Implementar scores interpretables para el panel. |
| 8 | Simulador retroactivo antes de promover decisiones | ⭕ Pendiente | Requiere dataset limpio y motor de backtesting. |
| 9 | Reportes post-sesión (win rate, drawdown evitado) | ⭕ Pendiente | Definir formato y automatización diaria. |
| 10 | Límites de confianza dinámicos según volatilidad/datos | ⭕ Pendiente | Incorporar heurísticas adaptativas durante scoring. |

## Fases de implementación

- **Fase 0 – Preparación (Completada)**: Validación automatizada (`infra_check --ensure-dirs`), directorios creados para ambos modos, comandos `make health`/`make smoke` documentados.
- **Fase 1 – Hardening base (En preparación)**: Restan ajustes en systemd, rotación de artefactos y alertas.
- **Fase 2 – Ciclo de pruebas (Planificada)**: Ejecutar smoke continuo, datasets simulados y panel en modo test.
- **Fase 3 – Cerebro modular (Planificada)**: Refactor de pipelines internos y métricas.
- **Fase 4 – Entrenamiento continuo (Planificada)**: Automatizar reentrenos/promociones.
- **Fase 5 – Go-live testnet (Planificada)**: Orquestar servicios completos en testnet hasta estabilidad.
- **Fase 6 – Promoción a real (Planificada)**: Replicar configuración con claves mainnet y activar monitoreo extendido.
