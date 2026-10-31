"""Copy the precomputed JSON the static site renders into site/data/. No model, no network."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
OUT.mkdir(parents=True, exist_ok=True)
for name in ("results.json", "eval.json", "meta.json"):
    src = ROOT / "data" / "outputs" / name
    # re-serialise compactly: smaller payload, same content
    (OUT / name).write_text(json.dumps(json.loads(src.read_text()), separators=(",", ":")))
print({p.name: p.stat().st_size for p in OUT.iterdir()})
