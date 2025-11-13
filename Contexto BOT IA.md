# Contexto BOT IA

Este documento resume la arquitectura actual del repositorio **SLS_Bot** y sirve como punto de partida cuando se abre un nuevo chat o cuando alguien más toma el relevo. Cada vez que modifiquemos archivos clave deberíamos regresar aquí y actualizar la sección correspondiente.

---

## Modos operativos (TEST vs REAL)
- El archivo `config/config.json` ahora sigue el esquema `shared + modes`. El modo activo se elige con `SLSBOT_MODE` (`test` por defecto).  
- Rutas sensibles (logs, excel, modelos) aceptan el token `{mode}` para mantener separados los datos de pruebas (`logs/test`, `excel/test`, `models/cerebro/test`) y producción (`.../real`).  
- El cargador (`bot/sls_bot/config_loader.py`) combina `shared` + `modes.<activo>` y expone `_active_mode`, `_available_modes` y `_mode_config_path`.  
- Siempre que arranques un servicio systemd o un proceso manual (bot, Cerebro, panel) exporta `SLSBOT_MODE` para evitar mezclar credenciales o datos.

---

## Directorios y servicios principales
| Ruta | Descripción |
| --- | --- |
| `bot/` | Backend FastAPI + webhook del bot (`sls_bot.app`), helpers de Excel, cliente Bybit y router de control (`app.main`). |
| `bot/cerebro/` | Servicio “Cerebro IA” que observa el mercado, genera decisiones y mantiene memoria/experiencias. Usa modelos por modo (`models/cerebro/<mode>`). |
| `panel/` | Panel Next.js 14 que consume la API (`/status`, `/cerebro/*`, `/pnl/diario`). Ejecutar `npm run dev/lint/build`. |
| `config/` | `config.sample.json` con la estructura multi-modo. Copiar a `config.json` (no versionar). |
| `logs/{mode}/` | Bridge logs, decisiones, PnL, estado de riesgo y datasets Cerebro segregados por modo. |
| `excel/{mode}/` | Libros `26. Plan de inversión.xlsx` vinculados a operaciones/eventos del modo correspondiente. |
| `scripts/` | Deploy (`scripts/deploy`), pruebas (`scripts/tests/e2e_smoke.py`), utilidades Python (`scripts/tools/*.py`) y el gestor `scripts/manage.sh`. |

---

## Archivos clave y propósito
- `bot/sls_bot/app.py`: Webhook principal, integra Bybit, risk-management, escritura Excel, logging y usa las rutas por modo. Helpers `utc_now*` y `_path_or_default` resuelven rutas relativas.  
- `bot/app/main.py`: API de control/panel. Expone `/status`, `/logs/*`, `/pnl/diario`, incluye el modo activo en la respuesta y lee los mismos directorios que el bot.  
- `bot/sls_bot/config_loader.py`: Parser robusto (comentarios, comas) + motor de perfiles (`modes`). Usa `SLSBOT_MODE` y tokens `{mode}` para generar rutas.  
- `bot/cerebro/service.py`: Servicio continuo del Cerebro. Guarda decisiones/experiencias en `logs/<mode>/cerebro_*.jsonl` y carga modelos desde `models/cerebro/<mode>/active_model.json`. Reporta el modo en `/cerebro/status`.  
- `bot/sls_bot/strategies/scalping.py`: Estrategia de scalping multi-factor pensada para el modo demo. Consume `ia_utils.latest_slice`, mezcla tendencia micro/macro, compresión y liquidez para decidir `LONG/SHORT`; si la confianza cae por debajo de `confidence_threshold` usa `force_trade_confidence` para seguir operando con riesgo reducido, aplica un colchón `fee_bps_round_trip` para cubrir comisiones, define metas diarias (`min_trades_per_day`, `daily_target_pct`), TTL (30 min) y backoff (`forced_loss_backoff`, `forced_backoff_minutes`). El backend registra `scalp_trades_today`, `scalp_profit_today`, `scalp_forced_entries` y genera `scalp_telemetry.jsonl`, `scalp_daily.jsonl` y `alerts.log`.  
- `bot/cerebro/intel.py`: Orquestador de inteligencia (agregador CryptoPanic + detector de ballenas/spoofing basado en orderbook). Inyecta `metadata.orderflow` y bloquea señales dudosas desde el PolicyEnsemble.  
- `bot/cerebro/train.py`: Entrenamiento ligero (logistic regression). `--mode` autodetecta rutas de dataset/modelos según el modo. Añade campo `mode` al artefacto.  
- `scripts/tools/promote_strategy.py`: Copia `active_model.json` desde el modo de prueba al real cuando las métricas superan los umbrales y opcionalmente archiva/reset el dataset de experiencias del modo prueba.  
- `scripts/tools/generate_arena_runs.py`: Genera archivos JSONL sintéticos con miles de estrategias para Arena/Autopilot (`--count 5000 --output arena/runs/arena_5000.jsonl`). Ajusta medias de pnl/drawdown/win rate y la semilla para repetir resultados.  
- `scripts/tools/arena_scoreboard.py`: Calcula victorias por estrategia (`--score-threshold`) y mantiene `arena/scoreboard.json` + `arena/champions.json` para promover automáticamente las que acumulen `--promotion-wins`.  
- `scripts/tools/infra_check.py`: Carga `config.json`, revisa variables obligatorias (`BYBIT_*`, `PANEL_API_TOKENS`, `CONTROL_*`) y confirma que `logs/{mode}` & `excel/{mode}` existen. Útil antes de desplegar.  
- `README.md`: Documentación general (instrucciones de entorno, pruebas, despliegue, explicación modos/prueba-real y comandos de entrenamiento/promoción).  
- `.env.example`: Ejemplo de variables, incluye `SLSBOT_MODE`, credenciales panel y Bybit.  
- `bot/tests/test_health.py`: Tests FastAPI ajustados para usar `logs/<mode>`; ejecutar `venv\Scripts\python -m pytest bot/tests -q`.

---

## Flujo recomendado (modo prueba → modo real)
1. **Infra check**: `python scripts/tools/infra_check.py --env-file .env` para validar credenciales y rutas.  
2. **Modo prueba**: `SLSBOT_MODE=test` al iniciar `sls_bot.app`, `app.main` y `cerebro.service`. Ejecutar `scripts/tests/e2e_smoke.py` para comprobar la API.  
3. **Entrenamiento**: `python -m cerebro.train --mode test --min-auc ...` genera artefactos en `models/cerebro/test/`.  
4. **Promoción**: `python scripts/tools/promote_strategy.py --source-mode test --target-mode real` copia el modelo a `models/cerebro/real/active_model.json` y rota el dataset de test (opcional).  
5. **Modo real**: iniciar servicios con `SLSBOT_MODE=real`, apuntando a llaves Bybit reales. El panel debe consumir la API del modo real para ver operaciones/cooldowns productivos.  
6. **Iterar**: tras cada promoción, entrenar un nuevo candidato en modo prueba para mantener un pipeline continuo de estrategias.

---

## Convenciones de mantenimiento
- **Cualquier cambio en rutas, config o comportamiento** debe reflejarse aquí (archivo nuevo o sección actualizada) para preservar el contexto histórico.  
- **Nombres de archivos**: usa rutas relativas (`bot/sls_bot/app.py`) para que sean clicables desde la CLI.  
- **Formato**: Markdown plano para mantener compatibilidad con cualquier editor. Añade secciones/separadores si crece el alcance.  
- **Versionado**: incluye este archivo en cualquier PR/commit que modifique la arquitectura o instructivos operativos. De ese modo siempre estará sincronizado con la base de código.

---

## Observabilidad y alertas (SLS_Bot 2V)
- **Generador de métricas**: `scripts/tools/metrics_business.py` consolida `logs/{mode}/pnl.jsonl` (trades + cierres diarios) y expone métricas Prometheus (`sls_bot_business_*`). Hay target directo:  
  `make metrics-business MODE=real METRICS_OUTPUT=/var/lib/node_exporter/textfile_collector/sls_bot_business.prom`.  
  Úsalo con un timer systemd (`sls-metrics-business.timer`) cada 5 min para actualizar el textfile collector de Node Exporter.
- **Reglas y alertas**: `docs/observability/prometheus_rules.yml` contiene recording/alert rules para detectar: falta de trades (30 min), resumen diario atrasado (>25 h), win rate <45 % (>=15 trades) y drawdown >4 %.  
  `docs/observability/alertmanager.yml` es la plantilla de rutas Slack (`#sls-alertas`) con labels `mode/service` listos para rutear por entorno.
- **Dashboard Grafana**: `docs/observability/grafana/sls_bot_control_center.json` muestra KPIs (PnL acumulado, win rate, PnL diario, alertas) con variable `$mode`. Importarlo apuntando al datasource Prometheus (`DS_PROMETHEUS`).
- **Procedimiento detallado**: `docs/observability/README.md` documenta el stack (textfile collector, promtool/alertmanager dry-run, systemd unit/timer).

## Resiliencia y failover
- `scripts/tools/failover_sim.py` orquesta el simulacro: por defecto recorre `sls-api.service`, `sls-cerebro.service` y `sls-bot.service`, captura `systemctl status` + `journalctl` y genera `logs/failover/failover_report_<timestamp>.log`.
- `make failover-sim` → dry-run. `sudo make failover-sim EXECUTE=1` reinicia realmente. Personaliza la lista con `FAILOVER_SERVICES="svc1,svc2"` y los tiempos con `FAILOVER_MAX_WAIT`.
- Ajusta `FAILOVER_LOG_DIR` si quieres guardar los reportes fuera de `/root/SLS_Bot/logs/failover`.
- Documenta cada ejercicio siguiendo `docs/operations/failover.md` (checklist y puntos del post-mortem).
- **Ejecución 2025-11-09**: inicialmente `sls-cerebro` falló por `ModuleNotFoundError: pandas` y `sls-bot` por un ExecStart apuntando a `/root/SLS_Bot/SLS_Bot/...`. Se corrigió reinstalando las deps IA en el venv y actualizando `/etc/systemd/system/sls-bot.service` (ahora ambos reportan `active`). Ver `logs/failover/failover_report_20251109_144707.log`.

## CI/CD y provisioning
- Workflow `ci.yml` (GitHub Actions) ejecuta `make test`, `npm run lint`, `npm run build` y publica el artefacto del panel en cada push/PR a `main`.
- `infra/ansible/` contiene `inventory.example.ini`, `provision.yml` y las plantillas systemd (`templates/*.service.j2`). El playbook instala paquetes base, clona el repo en `sls_bot_root`, crea el venv, instala deps IA/panel y registra los servicios.
- Usa `ansible-playbook -i inventory.ini provision.yml -e sls_bot_repo=git@...` para personalizar repo, rama, usuario o ruta. Completa `/etc/sls_bot.env` y `config/config.json` antes de arrancar servicios.
- Configura en GitHub los secrets `DEPLOY_HOST`, `DEPLOY_USER` y `DEPLOY_SSH_KEY` para habilitar el job de despliegue en Actions (si no existen, el job se omite automáticamente).
- `scripts/tools/cerebro_dataset_check.py` audita `logs/<mode>/cerebro_experience.jsonl` (min filas, win rate, símbolos requeridos, símbolo dominante). El training `cerebro.train` ahora aborta automáticamente si los umbrales (`--dataset-*`) no se cumplen.
- `risk.guardrails` (nuevo en `config.sample.json`) permite fijar `min_confidence`, `max_risk_pct`, límites por símbolo y un cap de volatilidad (ATR%). `_apply_guardrails` ajusta riesgo/leverage o bloquea la señal antes de enviar la orden, registrando cada hit en `state["guardrail_hits"]`.
- `scripts/tools/arena_rank.py` ranking multi-métrica para Arena/Autopilot (Sharpe, Calmar, Profit Factor, win rate). Úsalo antes de promover estrategias: `python scripts/tools/arena_rank.py runs/*.jsonl --min-trades 100 --max-drawdown 5 --json`.
- `scripts/tools/autopilot_summary.py` combina dataset check + ranking y genera un JSON listo para CI (o Slack). Ejemplo: `python scripts/tools/autopilot_summary.py --dataset logs/test/cerebro_experience.jsonl --runs arena/runs/*.jsonl --output-json metrics/autopilot_summary.json`.
- Target `make autopilot-summary` y el script `scripts/cron/autopilot_summary.sh` facilitan correrlo desde CI/cron; añade `SLACK_WEBHOOK_AUTOPILOT` para alertas y apunta `AUTOPILOT_PROM_FILE` al textfile collector.
- `scripts/tools/deploy_plan.py` (target `make deploy-plan`) lee el resumen Autopilot (`DEPLOY_PLAN_AUTOPILOT`), `risk_state.json`, `AUDIT_LOG`, estados de servicios (`DEPLOY_PLAN_SERVICES`) y el último reporte de failover para generar `metrics/deploy_plan.md`. Úsalo antes de cada comité Go/No-Go y adjunta el Markdown al acta.
- El panel muestra la tarjeta **Autopilot 2V** leyendo `/autopilot/summary`; asegúrate de programar el summary para que el Control Center refleje dataset health + ranking actualizado.
- Seguridad F4: `AUDIT_LOG` registra acciones `/control/*`, `RATE_LIMIT_REQUESTS/WINDOW` protegen los endpoints sensibles y `docs/security/politicas.md` resume la estrategia de secretos/rotaciones.
- `docs/operations/credentials_checklist.md` lista todos los secretos/envs por frente (Bybit, panel, Slack, backups, observabilidad, Vault). Úsalo cuando pases de modo sample a producción.
