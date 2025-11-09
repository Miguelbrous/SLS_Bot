Documento vivo para guiar la evolución hacia **SLS_Bot 2V**: una versión robusta, automatizada y lista para operar 24/7 con ciclos rápidos de mejora. Última actualización: 2025-11-06.

## Objetivo macro

> **Entregar un bot capaz de operar 24/7 en real con resiliencia de infraestructura, inteligencia de trading verificable y herramientas operativas que permitan iterar sin fricción.**

## Fases principales

| Fase | Nombre | Propósito | Criterios de salida |
|------|--------|-----------|---------------------|
| F0 | **Baseline estable** *(Completada)* | Servicios systemd, cronjobs, monitor guard, checklists de operación. | Guía 24/7 publicada, `make monitor-install`, cron ingest/autopilot parametrizados. |
| F1 | **Reliability & Ops** | Congelar infraestructura reproducible y pipelines de despliegue. | CI/CD multi-stage, backups automatizados, alertas accionables, runbooks cerrados. |
| F2 | **Estrategia & IA** | Elevar performance del Cerebro y estrategias evaluadas. | Dataset QoS > 90%, backtests reproducibles, autopilot con salvaguardas y explainability extendida. |
| F3 | **Experiencia & Panel** | Herramientas para operar y auditar en tiempo real. | Panel “Control Center” con KPIs, flujos promote/rollback self-service, reporting diario automatizado. |
| F4 | **Security & Compliance** | Cerrar gaps de seguridad, auditoría y gobernanza. | Control de acceso centralizado, auditoría de acciones, políticas de llaves y rotación. |
| F5 | **Go-live escalonado** | Pasar de testnet a real con criterios objetivos. | Checklist de producción cumplida, métricas de profit/risk en ventana piloto, firma de Go/No-Go. |

## Backlog por frente

### 1. Infraestructura & Operaciones (F1)
- **CI/CD**: pipeline GitHub Actions multi-stage (lint, tests, build panel, empaquetado release, deploy staging). Artefactos versionados.
- **Provisioning reproducible**: playbooks Ansible o Terraform para levantar nodos (usuarios, paquetes, systemd, cron, prom stack).
- **Backups automáticos**: snapshot diario de `logs/`, `models/`, `.env` cifrado usando restic + almacenamiento S3/GCS.
- **Observabilidad ampliada**: métricas negocio (PnL acumulado, drawdown, slippage) + dashboards Grafana 2V.
- **Alertas operativas**: Alertmanager con rutas para trading halt, data stale, autopilot fail, desbalance panel/API.
- **Chaos / resiliencia**: script de failover para reiniciar servicios y proveer reporte post-mortem.

### 2. Trading & Estrategia (F2)
- **Arena 2V**: ranking con métricas ponderadas (Sharpe, Calmar, profit factor, consistencia), simulación multi-parámetro, explainers.
- **Autopilot**:
  - Entrenamiento incremental vs batch, control de drift en features clave.
  - Librería de datos curados (particiones por modo, etiquetado manual).
  - Guard rails: límites de riesgo por símbolo, auto-disable si volatilidad > X.
- **Riesgo dinámico**: motor que ajusta tamaño de posición según drawdown global, volatilidad de sesión, liquidez de Bybit.
- **Testing**: backtest reproducible con datasets fijados, test de performance en CPU/GPU.

### 3. Datos & Integraciones
- **Ingesta reforzada**: colas externas (Redis/Kafka) opcional, reintentos, degradación controlada.
- **Data lake ligero**: bucket S3 con snapshots diarios + esquema Parquet para BI.
- **Feeds alternativos**: Deribit, Binance para cobertura cruzada; modular drivers.
- **Pipeline de etiquetado**: notebooks/scripts para validar señales, detectar outliers.

### 4. Panel & UX (F3)
- **Control Center**: vista única con estado servicios, KPIs trading, alarmas activas, botones promote/rollback.
- **Gestión de experimentos**: lanzar jobs de autopilot con presets, guardar historial de runs y comparativas.
- **Reportes**: panel diario/semanal exportable a PDF/Slack con PnL, win rate, drawdown, top estrategias, incidentes.
- **Accesos**: roles (view-only, operator, admin), toggles para activar guardias, escalado manual de riesgo.
- **API pública**: endpoints versionados con documentación (OpenAPI) y contratos fijos por release.

### 5. Seguridad & Compliance (F4)
- **Gestión secretos**: Vault o SOPS; rotación programada de keys Bybit, Slack, panel.
- **Auditoría**: log estructurado de acciones (deploys, promote, override guardias) + retención centralizada.
- **Hardening API**: rate limiting, detección de brute force, mTLS opcional, refresh tokens.
- **Política incidentes**: quién puede parar bot, qué se guarda, cómo reactivar.

### 6. Organización & Ritmo de entregas
- **Cadencia**: sprints de 2 semanas con entregable demostrable por frente.
- **Definition of Done**: código + docs + pruebas + monitoreo + checklist de despliegue.
- **Control de versiones**: ramas `main` (prod), `release/*` (hardening), `feature/*`; etiquetas semánticas (`v2.0.0-alpha`).
- **Comunicación**: tablero Kanban (Notion/Jira) con estados: Backlog → Ready → In Progress → In Review → Done.

## Gobernanza, dependencias y responsables

### Células y ownership

| Frente | Responsable principal | Apoyo cruzado | Dependencias clave | Slack/Canal |
|--------|----------------------|---------------|--------------------|-------------|
| Infra/Ops | `@infra-team` (SRE) | `@devops`, `@cloud-admin` | Acceso root, cuentas cloud, secrets SRE, pipeline GitHub Actions | `#sls-ops` |
| Estrategia & IA | `@quant-team` | `@data-eng`, `@analytics` | Dataset curado, resultados Arena, simulaciones, etiquetado manual | `#sls-quant` |
| Panel & UX | `@frontend-team` | `@product`, `@design` | APIs versionadas, tokens panel, contratos DTO, dashboards | `#sls-panel` |
| Seguridad & Compliance | `@secops-team` | `@legal`, `@audit` | Política de claves, acceso auditoría, Vault/SOPS, playbooks incidentes | `#sls-security` |

**Modelo RACI**  
- *Responsible*: célula listada en la tabla.  
- *Accountable*: `@product-owner` + `@cto` (aprueban hitos).  
- *Consulted*: equipos mencionados en “Apoyo cruzado”.  
- *Informed*: stakeholders externos (`finance`, `support`, partners).

### Dependencias externas críticas
- **Cloud**: proyectos GCP/AWS para backups y observabilidad.  
- **Bybit**: claves API rotativas + sandbox.  
- **Slack/Telegram**: canales de alertas y postmortems.  
- **Node Exporter / Prometheus remoto**: recolección de métricas productivas.  
- **Repositorio datasets**: bucket S3 `sls-data-lake` (definir permisos IAM).

## Hitos de control y entregables

| Hito | Fases cubiertas | Entregables clave | Due owner | Señales de salida |
|------|-----------------|-------------------|-----------|-------------------|
| **M1 – Infra estable** | F1 | CI/CD multi-stage (`ci.yml`) estable, alertas Slack ingest/autopilot, plan de backups + restore dry-run documentado | `@infra-team` | Pipeline verde 3 runs consecutivos, alerta simulada recibida, snapshot restaurado en staging |
| **M2 – Trading listo para piloto** | F2 + F3 (parcial) | Autopilot 2V con drift guard & explainers, Panel Control Center en `staging`, simulación 30d con PnL>0 y drawdown <= X% | `@quant-team` + `@frontend-team` | Informe simulación firmado, demo Control Center, checklist IA completado |
| **M3 – Seguridad cerrada** | F4 | Vault/SOPS productivo, rotación automática, auditoría end-to-end centralizada, playbooks incidentes aprobados | `@secops-team` | Rotación ejecutada sin downtime, log de auditoría disponible 30d, postmortem plantilla revisada |
| **M4 – Go/No-Go ventana real** | F5 | Checklist 24/7 completado, métricas tiempo real validadas, comité de aprobación con KPIs | `@product-owner` + Leads | Acta Go/No-Go, KPIs dentro de guardrails, plan rollback testado |

### Cadencia de revisión
- **Weekly sync** por frente (30 min).  
- **Revisión cross-team** quincenal (1 h) para alinear dependencias.  
- **Post-mortem** dentro de 48 h tras cualquier incidente de severidad alta.  
- **Quarterly planning** para refrescar roadmap 2V y asignar recursos.

## Documentos relacionados
- `docs/operations/operacion_24_7.md` – Guía detallada de operación continua.
- `Contexto BOT IA.md` – Estado diario y decisiones recientes.
- `README.md` – Referencias rápidas de comandos y automatizaciones.
- `docs/security/politicas.md` *(pendiente)* – Reglas de llaves, auditoría y respuestas a incidentes.
- `docs/operations/credentials_checklist.md` – Lista de secretos/envs que debes completar al pasar a producción.
