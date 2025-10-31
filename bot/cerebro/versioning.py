from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ModelVersion:
    path: Path
    metrics: Dict[str, float]
    created_at: str
    tag: str


class ModelRegistry:
    """Gestor ligero de versiones almacenadas como JSON en disco."""

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self) -> Path:
        return self.models_dir / "registry.json"

    def _load_metadata(self) -> Dict[str, dict]:
        path = self._metadata_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_metadata(self, payload: Dict[str, dict]) -> None:
        self._metadata_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def register(self, *, path: Path, metrics: Dict[str, float], tag: str) -> ModelVersion:
        metadata = self._load_metadata()
        version_id = tag or path.stem
        entry = {
            "path": str(path),
            "metrics": metrics,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tag": tag,
        }
        metadata[version_id] = entry
        self._save_metadata(metadata)
        return ModelVersion(path=path, metrics=metrics, created_at=entry["created_at"], tag=tag)

    def promote(self, version_id: str) -> Optional[ModelVersion]:
        metadata = self._load_metadata()
        entry = metadata.get(version_id)
        if not entry:
            return None
        active_path = self.models_dir / "active_model.json"
        src = Path(entry["path"])
        if not src.exists():
            return None
        active_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        metadata["_active"] = entry
        self._save_metadata(metadata)
        return ModelVersion(path=active_path, metrics=entry.get("metrics") or {}, created_at=entry["created_at"], tag=entry.get("tag") or "")

    def current(self) -> Optional[ModelVersion]:
        metadata = self._load_metadata()
        entry = metadata.get("_active")
        if not entry:
            return None
        return ModelVersion(path=Path(entry["path"]), metrics=entry.get("metrics") or {}, created_at=entry["created_at"], tag=entry.get("tag") or "")

    def rollback(self, previous_version_id: str) -> Optional[ModelVersion]:
        return self.promote(previous_version_id)
