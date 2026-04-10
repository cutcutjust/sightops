"""Notion 数据库检查 + 编辑工具。

用法:
    .venv/bin/python scripts/notion_editor.py          # 查看数据库属性
    .venv/bin/python scripts/notion_editor.py fix      # 添加/修复所有属性
    .venv/bin/python scripts/notion_editor.py create   # 创建全新数据库
"""
import asyncio
from notion_client import AsyncClient

from app.core.config import get_settings

s = get_settings()
client = AsyncClient(auth=s.notion_token)

REQUIRED_PROPS = {
    "名称": {"title": {}},
    "Platform": {"select": {}},
    "URL": {"url": {}},
    "Relevance": {"number": {}},
    "Likes": {"number": {}},
    "Tags": {"multi_select": {}},
    "Collected": {"date": {}},
    "Status": {"select": {}},
    "Author": {"rich_text": {}},
    "Published URL": {"url": {}},
}


async def inspect():
    """查看数据库所有属性。"""
    for label, db_id in [
        ("Research", s.notion_research_db_id),
        ("Template", s.notion_template_db_id),
        ("Draft", s.notion_draft_db_id),
    ]:
        db = await client.databases.retrieve(db_id)
        title = db.get("title", [{}])[0].get("plain_text", "?") if db.get("title") else "?"
        props = db.get("properties", {})
        print(f"\n{'=' * 50}")
        print(f"{label} DB: {title}")
        print(f"ID: {db_id}")
        print(f"Properties ({len(props)}):")
        for name, info in props.items():
            print(f"  {name}: {info.get('type', '?')}")


async def fix_research_db():
    """修复 Research 数据库 — 添加缺失属性。"""
    db_id = s.notion_research_db_id
    db = await client.databases.retrieve(db_id)
    existing = set(db.get("properties", {}).keys())
    print(f"当前属性: {existing}")

    for name, schema in REQUIRED_PROPS.items():
        if name in existing:
            print(f"  ✓ '{name}' 已存在")
            continue
        prop_type = next(iter(schema.keys()))
        print(f"  + 添加 '{name}' ({prop_type})...", end=" ")
        try:
            resp = await client.databases.update(
                db_id,
                properties={name: schema}
            )
            if name in resp.get("properties", {}):
                print("成功")
            else:
                print("已发送但未出现在响应中")
        except Exception as e:
            print(f"失败: {e}")

    print("\n修复后:")
    await inspect()


async def create_new_research_db():
    """创建全新的 Research 数据库。"""
    # 需要先用一个 page 作为 parent
    # 搜索已有的 top-level page
    results = await client.search()
    pages = [r for r in results.get("results", []) if r.get("object") == "page"]

    # 找 workspace 级别的 page
    for p in pages:
        parent = p.get("parent", {})
        if parent.get("type") == "workspace":
            page_id = p["id"]
            title = ""
            for k, v in p.get("properties", {}).items():
                if v.get("type") == "title" and v.get("title"):
                    title = v["title"][0].get("plain_text", "")
                    break
            print(f"使用页面: {page_id} | {title}")

            db = await client.databases.create(
                parent={"type": "page_id", "page_id": page_id},
                title=[{"type": "text", "text": {"content": "XAgent Research"}}],
                properties=REQUIRED_PROPS,
            )
            print(f"\n新数据库创建成功: {db['id']}")
            print(f"URL: {db.get('url', '')}")
            print(f"\n请更新 .env 中的 NOTION_RESEARCH_DB_ID={db['id']}")
            return

    print("未找到可用的 workspace 级别页面")


async def main():
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "fix":
        await fix_research_db()
    elif cmd == "create":
        await create_new_research_db()
    else:
        await inspect()


if __name__ == "__main__":
    asyncio.run(main())
