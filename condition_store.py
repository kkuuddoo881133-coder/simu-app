from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


STORE_PATH = Path("saved_conditions/conditions.jsonl")
JST = ZoneInfo("Asia/Tokyo")


def save_condition(payload: dict, path: Path | str = STORE_PATH) -> Path:
    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "saved_at_jst": datetime.now(JST).isoformat(timespec="seconds"),
        **payload,
    }
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return store_path


def load_conditions(path: Path | str = STORE_PATH) -> list[dict]:
    store_path = Path(path)
    if not store_path.exists():
        return []
    records = []
    with store_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

