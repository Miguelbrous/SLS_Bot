#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / '.env'
DEFAULT_CONFIG = ROOT / 'config' / 'demo_emitter.json'


def load_env_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def start_process(cmd, env):
    return subprocess.Popen(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description='Orquestador demo (API + emisor)')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='Ruta al demo_emitter.json')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', default='8080')
    parser.add_argument('--once', action='store_true', help='Envia un batch y termina (emisor)')
    parser.add_argument('--dry-run', action='store_true', help='Emisor sin HTTP')
    parser.add_argument('--only-emitter', action='store_true')
    parser.add_argument('--only-api', action='store_true')
    args = parser.parse_args()

    env = os.environ.copy()
    file_env = load_env_file(ENV_PATH)
    env.update({k: v for k, v in file_env.items() if k and v})
    env.setdefault('SLSBOT_MODE', 'demo')

    processes = []
    try:
        if not args.only_emitter:
            api_cmd = [sys.executable, '-m', 'uvicorn', 'bot.sls_bot.app:app', '--host', args.host, '--port', args.port]
            processes.append(start_process(api_cmd, env))
        if not args.only_api:
            emitter_cmd = [sys.executable, 'scripts/demo_emitter.py', '--config', str(args.config)]
            if args.once:
                emitter_cmd.append('--once')
            if args.dry_run:
                emitter_cmd.append('--dry-run')
            processes.append(start_process(emitter_cmd, env))
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

if __name__ == '__main__':
    main()
