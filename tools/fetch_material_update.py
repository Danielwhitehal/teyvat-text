import asyncio
import json
import os
import ambr
from ambr import AmbrAPI

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
LOCAL_DATA_DIR = str(ROOT / "data" / "material")
OUTPUT_DIR = str(ROOT / "staging" / "material")

def get_local_names():
    names = set()
    for f in os.listdir(LOCAL_DATA_DIR):
        if f.endswith(".json"):
            names.add(f[:-5])
    return names

def convert_material(detail):
    return {
        "name": detail.name,
        "description": detail.description,
        "type": detail.type,
        "rarity": detail.rarity,
    }

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    local_names = get_local_names()
    async with AmbrAPI(lang=ambr.Language.CHS) as client:
        mats = await client.fetch_materials()
        new_count = 0
        for m in mats:
            if m.name in local_names:
                continue
            try:
                detail = await client.fetch_material_detail(m.id)
                data = convert_material(detail)
                out_path = os.path.join(OUTPUT_DIR, f"{m.name}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                new_count += 1
                print(f"Saved: {m.name} -> {out_path}")
            except Exception as e:
                print(f"FAILED: {m.name}: {e}")
        print(f"\nDone. {new_count} new materials saved.")

if __name__ == "__main__":
    asyncio.run(main())
