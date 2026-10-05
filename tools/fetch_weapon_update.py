import asyncio
import json
import os
import ambr
from ambr import AmbrAPI
from pydantic import ValidationError

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
LOCAL_DATA_DIR = str(ROOT / "data" / "weapon")
OUTPUT_DIR = str(ROOT / "staging" / "weapon")

def get_local_names():
    names = set()
    for f in os.listdir(LOCAL_DATA_DIR):
        if f.endswith(".json"):
            names.add(f[:-5])
    return names

async def fetch_weapon_story(client, story_id):
    try:
        return await client.fetch_readable(f"Weapon{story_id}")
    except Exception:
        return ""

async def get_weapon_detail(client, wid):
    try:
        return await client.fetch_weapon_detail(wid)
    except ValidationError:
        raw = await client._request(f"weapon/{wid}", use_cache=True)
        return raw.get('data', raw)

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    local_names = get_local_names()
    async with AmbrAPI(lang=ambr.Language.CHS) as client:
        weapons = await client.fetch_weapons()
        new_count = 0
        for w in weapons:
            if w.name in local_names:
                continue
            try:
                detail = await get_weapon_detail(client, w.id)
                if hasattr(detail, 'story_id'):
                    story = await fetch_weapon_story(client, detail.story_id)
                    story_id = detail.story_id
                elif isinstance(detail, dict) and 'storyId' in detail:
                    story = await fetch_weapon_story(client, detail['storyId'])
                    story_id = detail['storyId']
                else:
                    story = ""
                    story_id = None
                if hasattr(detail, 'id'):
                    data = {
                        "id": detail.id,
                        "name": detail.name,
                        "type": detail.type,
                        "description": detail.description,
                        "story": story
                    }
                else:
                    data = {
                        "id": detail['id'],
                        "name": detail['name'],
                        "type": detail['type'],
                        "description": detail['description'],
                        "story": story
                    }
                out_path = os.path.join(OUTPUT_DIR, f"{w.name}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                new_count += 1
                print(f"Saved: {w.name}")
            except Exception as e:
                print(f"FAILED: {w.name}: {e}")
        print(f"\nDone. {new_count} new weapons saved.")

if __name__ == "__main__":
    asyncio.run(main())
