import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
LOCAL_ARTIFACT_DIR = Path(str(ROOT / "data" / "artifact"))
OUTPUT_DIR = Path(str(ROOT / "staging" / "artifact"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

local_names = set()
for f in LOCAL_ARTIFACT_DIR.glob("*.json"):
    local_names.add(f.stem)
print(f"本地已有圣遗物: {len(local_names)} 个")

import ambr

SLOT_MAP = {
    "EQUIP_BRACER": "生之花",
    "EQUIP_NECKLACE": "死之羽",
    "EQUIP_SHOES": "时之沙",
    "EQUIP_RING": "空之杯",
    "EQUIP_DRESS": "理之冠",
}

async def fetch_artifact_with_story(client, artifact_id):
    detail = await client.fetch_artifact_set_detail(str(artifact_id))
    artifact_data = {
        "id": detail.id,
        "name": detail.name,
        "max_rarity": detail.rarity_list[-1] if detail.rarity_list else None,
        "source": [],
        "pieces": []
    }
    if detail.route:
        artifact_data["source"].append({"name": detail.route, "type": "single"})
    for art in detail.artifacts:
        slot_key = art.pos
        slot_name = SLOT_MAP.get(slot_key, slot_key)
        story_text = ""
        icon_path = art.icon_path
        if icon_path and "UI_RelicIcon_" in icon_path:
            suffix = icon_path.replace("UI_RelicIcon_", "")
            readable_id = f"Relic{suffix}"
            try:
                story_text = await client.fetch_readable(readable_id)
            except Exception as e:
                print(f"  警告: 获取 story 失败 ({readable_id}): {e}")
        artifact_data["pieces"].append({
            "slot": slot_name,
            "slot_key": slot_key,
            "name": art.name,
            "description": art.description,
            "story": story_text
        })
    return artifact_data

async def main():
    print("正在连接 Yatta API...")
    async with ambr.AmbrAPI(lang=ambr.Language.CHS) as client:
        print("正在获取圣遗物套装列表...")
        artifact_sets = await client.fetch_artifact_sets()
        print(f"远程共 {len(artifact_sets)} 套圣遗物")
        new_artifacts = []
        for idx, aset in enumerate(artifact_sets, 1):
            name = aset.name
            if name in local_names:
                continue
            print(f"[{idx}/{len(artifact_sets)}] 新增: {name} (ID:{aset.id})")
            artifact_data = await fetch_artifact_with_story(client, str(aset.id))
            new_artifacts.append(artifact_data)
            safe_name = name.replace("/", "_").replace("\\", "_")
            filename = f"{safe_name}.json"
            filepath = OUTPUT_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(artifact_data, f, ensure_ascii=False, indent=2)
            print(f"  已保存: {filepath.name}")
            await asyncio.sleep(0.15)
        print(f"\n新增保存: {len(new_artifacts)} 套")
        summary_file = OUTPUT_DIR / "_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "total_remote": len(artifact_sets),
                "local_count": len(local_names),
                "new_count": len(new_artifacts),
                "new_artifacts": [{"id": a["id"], "name": a["name"]} for a in new_artifacts]
            }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
