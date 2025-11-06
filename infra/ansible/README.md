# Ansible – Provisioning reproducible para SLS_Bot 2V

Este playbook automatiza el bootstrap de un nodo SLS_Bot (usuario de servicio, paquetes base, clon del repo, bootstrap de servicios/systemd, cronjobs y monitor guard).

## Requisitos

- Python/Ansible 2.13+ en la máquina de control (`pip install ansible`).
- Acceso SSH con privilegios sudo al host de destino.
- Claves/API almacenadas en Vault o variables de entorno (no las añadas al repo).

## Estructura

```
infra/ansible/
├── inventory.sample.ini    # Ejemplo de inventario (duplica como inventory.prod.ini, etc.)
├── playbooks/
│   └── site.yml            # Playbook principal
└── roles/
    └── sls_bot/
        ├── defaults/main.yml
        ├── tasks/main.yml
        └── templates/env.j2
```

### Variables relevantes

`roles/sls_bot/defaults/main.yml` expone:

- `sls_user`: usuario de servicio (default `sls`).
- `app_root`: ruta donde se desplegará el repositorio (`/opt/SLS_Bot`).
- `repo_url` / `repo_branch`: origen y rama a clonar.
- `system_packages`: paquetes base que se instalarán (git, python3-venv, nodejs, docker…).
- `bootstrap_autorun`: si es `true`, ejecuta `scripts/deploy/bootstrap.sh` y `make monitor-install`.
- `env_template_path`: plantilla `.env` que se renderiza en `/etc/sls_bot.env`.
- `restic_enabled` / `restic_environment_file`: si `true`, despliega `sls-backup.service/timer` (debes crear el archivo con las variables Restic via vault).

Puedes sobreescribirlas en `group_vars` o `host_vars`.

## Uso

1. Duplica el inventario:
   ```bash
   cp infra/ansible/inventory.sample.ini infra/ansible/inventory.staging.ini
   # Edita ansible_host, app_root, repo_url, etc.
   ```

2. Exporta claves sensibles (ej.: tokens, claves Bybit) antes de correr Ansible:
   ```bash
   export SLS_PANEL_TOKEN_PROD=...
   export SLS_BYBIT_KEY=...
   ```

3. Ejecuta el playbook:
   ```bash
   ansible-playbook -i infra/ansible/inventory.staging.ini infra/ansible/playbooks/site.yml
   ```

   - Añade `--limit staging` para un host concreto.
   - Usa `-e bootstrap_autorun=false` si quieres revisar manualmente antes de correr bootstrap.

4. Verifica:
   ```bash
   ssh staging "systemctl status sls-api sls-bot sls-cerebro"
   ssh staging "journalctl -u sls-monitor.timer"
   ```

## Target Makefile

El Makefile expone `make provision STAGE=staging` que invoca `ansible-playbook` usando el inventario correspondiente (`infra/ansible/inventory.$(STAGE).ini`).

## Buenas prácticas

- Guarda inventarios reales fuera del repo o cifrados con `ansible-vault`.
- Integra el playbook en el pipeline CI/CD (job de infraestructura) usando `ansible-playbook --syntax-check` y `--check` antes de aplicar cambios.
- Documenta en `docs/operations/operacion_24_7.md` cualquier override específico del entorno.
