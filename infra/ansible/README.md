# Ansible provisioning

Este playbook entrega un nodo listo para correr SLS_Bot (servicios API, Bot y Cerebro). Pasos:

1. Crea un inventario:
   ```
   cp inventory.example.ini inventory.ini
   ```
   Edita la IP/usuario y, si usas claves SSH, añade `ansible_ssh_private_key_file`.

2. Ejecuta el playbook:
   ```
   ansible-playbook -i inventory.ini provision.yml \
     -e sls_bot_repo=git@github.com:tu-org/SLS_Bot.git \
     -e sls_bot_revision=main
   ```

3. Completa `/etc/sls_bot.env` y `{{ sls_bot_root }}/config/config.json` con credenciales reales antes de arrancar los servicios.

Personaliza `sls_bot_root`, `sls_bot_user` o los servicios en `provision.yml` según tu infraestructura.
