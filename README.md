# teyvat-text

原神游戏文本数据集 + 采集/校正/可视化工具链。

从 Yatta/Ambr API 采集各类文本，建立树索引，生成可浏览的 HTML 查看器；任务文本另按 BWIKI 校正。

> ⚠️ **非官方粉丝项目**：与米哈游 / HoYoverse 无隶属关系，游戏文本/数据版权归其所有。
> **代码**（`tools/`、`serve.py`）为 MIT；**数据**（`data/`）不在 MIT 范围内。详见 [`LICENSE`](LICENSE) 与 [`NOTICE.md`](NOTICE.md)。

## 目录结构

```
teyvat-text/
├── data/                     # 数据成果
│   ├── quest/                # 任务对话（travellog）
│   ├── artifact/             # 圣遗物
│   ├── book/                 # 书籍
│   ├── character/            # 角色
│   ├── material/             # 材料
│   ├── weapon/               # 武器
│   └── trees/                # 树索引 *_tree.json
├── tools/                    # 所有脚本
│   ├── paths.py              # 路径中枢（全项目唯一路径来源）
│   ├── fetch_*_update.py     # 六块增量拉取
│   ├── regenerate_trees.py   # 重建非任务树索引
│   ├── generate_html_v2.py   # 生成 HTML 查看器
│   ├── correct/              # 校正脚本
│   └── quest_ops/            # 任务提取/比对/挂树工具集
├── web/                      # 查看器（quest_tree.html）
├── staging/                  # 拉取暂存（不进仓）
├── serve.py                  # 跨平台启动本地查看器（HTTP 服务 + 开浏览器）
└── docs/                     # TECHNICAL_DOC.md（权威说明）
```

## 快速开始

### 依赖

- **Python ≥ 3.10**（开发环境 3.14）
- 依赖见 `requirements.txt`：

```bash
pip install -r requirements.txt
```

### 更新数据

```bash
python tools/fetch_quest_update.py        # 任务；--dry 只列新增
python tools/fetch_artifact_update.py
python tools/fetch_book_update.py
python tools/fetch_character_update.py
python tools/fetch_material_update.py
python tools/fetch_weapon_update.py
```

新增文件落在 `staging/{块名}/`。人工确认后复制进 `data/{块名}/`：

| staging | data |
|---|---|
| `staging/quest/` | `data/quest/` |
| `staging/artifact/` | `data/artifact/` |
| `staging/book/` | `data/book/` |
| `staging/character/` | `data/character/` |
| `staging/material/` | `data/material/` |
| `staging/weapon/` | `data/weapon/` |

### 重建索引 + 生成查看器

```bash
python tools/regenerate_trees.py          # 非任务树（任务树手工维护，见 docs）
python tools/generate_html_v2.py          # → web/quest_tree.html
```

### 查看

运行 `python serve.py`（起本地服务并自动打开 `web/quest_tree.html`）。
> 查看器用 `fetch` 运行时读取 `data/`，浏览器在 `file://` 下会拦截，**不能直接双击 HTML**，必须经此 HTTP 服务打开。

## 路径约定

所有脚本通过 `tools/paths.py` 定位仓库根，**不硬编码绝对路径**，可整仓移动/跨平台。
运行时产物（`staging/`、`__pycache__`、`.cache/`、校正中间产物）均在 `.gitignore` 中。

## 许可

- **源代码**：MIT License，见 [`LICENSE`](LICENSE)。
- **数据与文本**（`data/`）：版权归米哈游 / HoYoverse，**不在 MIT 范围内**；来源、使用与 AI 条款见 [`NOTICE.md`](NOTICE.md)。

## 数据格式 / 校正流程

见 `docs/TECHNICAL_DOC.md`（唯一权威说明）。
