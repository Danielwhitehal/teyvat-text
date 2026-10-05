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
LOCAL_BOOK_DIR = Path(str(ROOT / "data" / "book"))
OUTPUT_DIR = Path(str(ROOT / "staging" / "book"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 读取本地已有书籍 id（取 JSON 的 id 字段，稳健：改名/改标题都不影响识别）
local_ids = set()
for f in LOCAL_BOOK_DIR.glob("*.json"):
    try:
        with open(f, "r", encoding="utf-8") as fh:
            idv = json.load(fh).get("id")
    except Exception:
        idv = None
    if idv is not None:
        local_ids.add(idv)
print(f"本地已有书籍(id): {len(local_ids)} 本")

import ambr

async def fetch_book_with_text(client, book_id, route=""):
    """获取书籍详情并包含每卷的full_text"""
    detail = await client.fetch_book_detail(str(book_id))
    
    book_data = {
        "id": detail.id,
        "name": detail.name,
        "route": route,
        "rank": detail.rarity,
        "volumes": []
    }
    
    for vol in detail.volumes:
        full_text = ""
        try:
            full_text = await client.fetch_readable(f"Book{vol.story_id}")
        except Exception as e:
            print(f"  警告: 获取 full_text 失败 (Book{vol.story_id}): {e}")
        
        book_data["volumes"].append({
            "volume_id": vol.id,
            "volume_name": vol.name,
            "description": vol.description,
            "full_text": full_text
        })
    
    return book_data

async def main():
    print("正在连接 Yatta API...")
    async with ambr.AmbrAPI(lang=ambr.Language.CHS) as client:
        print("正在获取书籍列表...")
        books = await client.fetch_books()
        print(f"远程共 {len(books)} 本书")
        
        new_books = []
        for idx, book in enumerate(books, 1):
            name = book.name
            # 跳过空名称的书籍
            if not name or name.strip() == "":
                continue
            if book.id in local_ids:
                continue
            
            print(f"[{idx}/{len(books)}] 新增: {name} (ID:{book.id})")
            book_data = await fetch_book_with_text(client, book.id, book.route)
            new_books.append(book_data)
            
            safe_name = name.replace("/", "_").replace("\\", "_")
            filename = f"{safe_name}_{book.id}.json"
            filepath = OUTPUT_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(book_data, f, ensure_ascii=False, indent=2)
            print(f"  已保存: {filepath.name} ({len(book_data['volumes'])}卷)")
            
            await asyncio.sleep(0.15)
        
        print(f"\n===== 总结 =====")
        print(f"远程总计: {len(books)} 本")
        print(f"本地已有(id): {len(local_ids)} 本")
        print(f"新增保存: {len(new_books)} 本")
        
        summary_file = OUTPUT_DIR / "_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "total_remote": len(books),
                "local_count": len(local_ids),
                "new_count": len(new_books),
                "new_books": [{"id": b["id"], "name": b["name"]} for b in new_books]
            }, f, ensure_ascii=False, indent=2)
        print(f"\n汇总已保存: {summary_file}")

if __name__ == "__main__":
    asyncio.run(main())
