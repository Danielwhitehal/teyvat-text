# 原神文本数据工程 — 技术文档

> 本项目 = 从 Yatta/Ambr 拉取各类文本 → 建索引 → 生成 HTML 查看器；其中**各数据块（视需要）再按 BWIKI 校正文本**。
> 仓库：`teyvat-text`（可整仓移动 / 换盘 / 被 fork 到任意路径，无绝对路径依赖）。
>
> **两块流程**：
> 1. **数据更新（全 6 块通用）**：`fetch_*_update.py` 拉取 → 合并到数据目录 → `regenerate_trees.py` 建索引 → `generate_html_v2.py` 出 HTML。见 §2、§3；详步骤另见 `README.md`。
> 2. **校正工作（按块推进）**：见 **§4**。任务块（§4.1）已完成；其余 5 块（§4.2–§4.6）为**待做框架**。
>
> **接手一句话**：先读 §0、§2、§4.1.5（**防改坏**）。**任务校正别整段重跑**；新块照 §4 对应小节搭。

## 0. 上手要求（必读）
- **环境**：Windows / PowerShell 5.1。脚本分两类：`fetch_*`（需 `pip install ambr aiohttp`）与 `tools\correct\*`（仅标准库，Python 3.14 验证）。GBK 终端里中文可能乱码，属显示问题，文件本身都是 UTF-8。
- **路径机制**：全项目路径统一由 `tools\paths.py` 提供（它从自身位置向上找到同时含 `data\` + `tools\` 的目录作为仓库根）。**脚本里没有任何绝对路径**，整仓移动/换机器/跨平台均可用。新增脚本请 `from paths import ROOT`，不要再写死路径。
- **目录纪律**：脚本只落在 `tools\`；运行时中间产物落 `staging\`（拉取暂存）与 `tools\correct\bwiki_data\`（校正爬取）；数据成果落在 `data\`。`staging\`、`bwiki_data\`、`__pycache__`、`.cache\` 均在 `.gitignore`，不进仓。
- **只增、不重跑**（任务校正）：任务目录里已有 `_bwiki.json` 会被 skip（`--batch`）/ 拒绝（单任务）；`--force` 只在人类明确要求时用。
- **不代做精校**：脚本只做机械转换，文本措辞/游戏内标记的定稿由人类完成。
- **改脚本前先备份**（旧的 `校正\_backup\{时间戳}\` 已在收尾时删除，需自行新建）。

## 1. 目录与关键路径

```
teyvat-text\
├── data\                          ← 数据成果
│   ├── quest\                     ← 任务（原 travellog_json）
│   ├── artifact\  book\           ← 圣遗物 / 书籍
│   ├── character\ material\       ← 角色 / 材料
│   ├── weapon\                    ← 武器
│   └── trees\                     ← 树索引：aq/eq/legend/wq_quest_tree.json + {artifact,book,character,material,weapon}_tree.json + _废弃任务清单.md
├── tools\                         ← 所有脚本
│   ├── paths.py                   ← 路径中枢（全项目唯一路径来源）
│   ├── fetch_{artifact,book,character,material,weapon,quest}_update.py  ← 从 Ambr 拉新数据
│   ├── regenerate_trees.py        ← 从数据目录重建非任务类索引（*_tree.json）
│   ├── generate_html_v2.py        ← 由索引生成 quest_tree.html（含全部块）
│   ├── correct\                   ← 校正脚本（原「校正\{块名}校正工作」）
│   │   ├── run_task_simpler.py / run_ids.py / fetch_bwiki_v2.py / fetch_bwiki_single.py / reparse_bwiki.py / restore_yatta.py
│   │   ├── analyze_books.py
│   │   └── bwiki_data\            ← 校正爬取中间产物（运行时按需重建，进 .gitignore）
│   └── quest_ops\                 ← 任务提取/比对/挂树工具集（原「任务更新专项优化」，§4.1.7）
├── web\                           ← 查看器
│   └── quest_tree.html            ← ⭐ 唯一 HTML 查看器（须经 HTTP 服务打开）
├── serve.py                       ← 跨平台启动本地查看器（HTTP 服务 + 开浏览器）
├── staging\                       ← fetch_* 的拉取产物（原「更新」，合并进数据目录后清空，进 .gitignore）
├── docs\
│   └── TECHNICAL_DOC.md           ← 本文档
├── README.md                      ← 「更新数据 + 生成 HTML」流程
└── .gitignore
```

**路径速查**（仓库根由 `tools\paths.py` 自动定位，文档中一律用相对路径）
- 数据根：`data\`
- 树索引：`data\trees\`
- HTML：`web\quest_tree.html`
- 任务校正脚本：`tools\correct\`
- 任务爬取中间产物：`tools\correct\bwiki_data\`（**当前为空**，运行时按需重建）
- 提取/挂树工具集：`tools\quest_ops\`

## 2. 数据块总览 + 更新流程

| 数据块 | 数据源 | 数据目录（`data\`） | 拉取脚本（`tools\`） | 树索引（`data\trees\`） | HTML 类型 |
|---|---|---|---|---|---|
| **任务** | Ambr（文本另经 BWIKI 校正，§4.1） | `quest\` | `fetch_quest_update.py`（新内核，§4.1.7） | `aq/eq/legend/wq_quest_tree.json`（**手工维护**） | `quest` |
| **圣遗物** | Ambr | `artifact\` | `fetch_artifact_update.py` | `artifact_tree.json`（自动） | `artifact` |
| **书籍** | Ambr | `book\` | `fetch_book_update.py` | `book_tree.json` | `book` |
| **角色** | Ambr | `character\` | `fetch_character_update.py` | `character_tree.json` | `character` |
| **材料** | Ambr | `material\` | `fetch_material_update.py` | `material_tree.json` | `material` |
| **武器** | Ambr | `weapon\` | `fetch_weapon_update.py` | `weapon_tree.json` | `weapon` |

**更新流程（4 步）**：
1. **拉取**：运行对应 `tools\fetch_*_update.py`，自动比对本地已有文件、只拉新增；输出到 `staging\{块名}\`。
2. **合并**：把 `staging\{块名}\` 里的文件**手动**复制进上表对应数据目录，清空该临时子目录。
3. **建索引**：`python tools\regenerate_trees.py` —— 扫描数据目录，重建 5 个非任务类 `*_tree.json`（**不含**任务树）。
4. **出 HTML**：`python tools\generate_html_v2.py`。

> 文件名与 ID 约定：以 **ID / 文件名** 唯一确定（书籍/武器多为 `{ID}_{名}.json`，角色为 `{角色ID}-{元素}.json` 等）；具体以数据目录与 `regenerate_trees.py` 逻辑为准。
> 任务树索引**手工维护**（编辑 `data\trees\` 里的 `aq/eq/iq/legend/wq_quest_tree.json`）；其它 5 块索引由 `regenerate_trees.py` 自动生成。

## 3. 各块数据结构（HTML 渲染所读字段）

- **任务 quest**：见 §4.1.6。
- **圣遗物 artifact**：`name`、`max_rarity`、`source`；`pieces[]`（`slot` 部位、`name`、`description`、`story` 圣遗物故事）。（`affix_list` 效果描述已删除，见 §4.2。）
- **书籍 book**：`name`；`volumes[]`（`volume_name` 卷名、`description`、`full_text` 全文）。
- **角色 character**：`name`、`title` 称号、`constellation` 命之座、`story{}`（角色故事）、`quotes{}`（语音）。（`cv` 等已在 §4.4 精简掉。）
- **材料 material**：`name`、`rarity`、`type`、`description`。
- **武器 weapon**：`name`、`rank` 星级、`type`、`description`、`story` 武器故事。

---

# 4. 校正工作

> 每个数据块一节。**§4.1 任务**已完成（模板可参照）；**§4.2–§4.6** 只搭了架子，做的时候往对应小节里填内容即可，**不用再改文档骨架**。
> 各块的"文本源"都是 Ambr 的官方文本；**是否再做 BWIKI 校对、以及对应字段与页名，需先与人类确认范围**。

## 4.1 任务（travellog） — ✅ 已完成（截至霜月；至冬暂停）

### 4.1.1 流程与命令
```powershell
# 先看要处理哪些（不抓取）
python tools\correct\run_task_simpler.py --batch --tree=wq --block=<区域> --dry
# 正式处理
python tools\correct\run_task_simpler.py --batch --tree=wq --block=<区域>
# 单任务 / 按 ID（查漏补缺、补爬）
python tools\correct\run_task_simpler.py "任务名" ID
python tools\correct\run_ids.py 75230 74141 --force
```
- `--tree`：`eq | aq | legend | wq`（`lq`=`legend`；`iq` 保留但不进 HTML）；`--block`：该树**顶层**的版本块/区域名；也可直接给 `.json` 路径。
- 每任务：定位 travellog → 备份 `_yatta.json` → 抓取（逐故事 BWIKI）→ 选源 → 替换 → 折叠边界 → 写回 → 校验。
- 反爬约 6 秒/故事 + 每 5 个停 30 秒 → **命令超时设 30~60 分钟**。
- 处理完**必做**：`python tools\generate_html_v2.py`。

### 4.1.2 选源 / 替换 / 异常规则
- **选源（逐故事）**：BWIKI 非空且 **≥ 本地(Yatta)×70%** → 用 BWIKI；否则用本地。
- **替换**：role `玩家→旅行者`、`空/荧→空`、`荧/空→荧`；text `他/她→他`、`他们/她们→他们`、`哥哥/姐姐→哥哥`。
- **致命异常**（残留 `}}` / 单故事 >500KB）→ **中止、不写回**。

### 4.1.3 脚本参考（`tools\correct\`）
| 脚本 | 作用 | 备注 |
|---|---|---|
| `run_task_simpler.py` | ⭐ 主入口：批量/单任务；定位→备份→抓取→选源→替换→折叠→写回→校验 | 自足（抓取/解析已内联） |
| `run_ids.py` | 按 ID 批处理（查漏补缺、`--force` 补爬） | `import run_task_simpler` |
| `fetch_bwiki_v2.py` | 抓取/解析库 | 被下两个 import |
| `fetch_bwiki_single.py` | 单故事抓取小工具 | `import fetch_bwiki_v2` |
| `reparse_bwiki.py` | 离线重解析（用 `_wikitext.json` 重建 `_bwiki.json`） | **需 `bwiki_data`，当前为空 → 跑不动** |
| `restore_yatta.py` | 回滚 travellog 到 Yatta | **需 `bwiki_data`，当前为空 → 跑不动** |

> **路径机制（迁移后）**：全项目路径统一由 `tools\paths.py` 提供（向上定位仓库根），脚本内**不再有任何绝对路径**，可整仓移动/换机器 ✓。脚本间 import 用 `dirname(__file__)`：**7 个校正脚本同在 `tools\correct\`** ✓。`_需留意清单.md` 与 `bwiki_data\` 现均落在 `tools\correct\` 下，且 `reparse_bwiki.py` 与其它脚本**已统一到同一个 `bwiki_data\`**（原「不一致」问题已修复）。
> **页名定位（2026-10 增强）**：`process_quest` 以 story 标题为 BWIKI 页名，候选顺序 **`本名 → 本名（任务） → 本名（章节名）`**；主名有剧情且条数 ≥ 本地×70% 则不再试备用页。专门应对「同名页」陷阱（实例：1703 幕「邪眼」→ 正确页 `邪眼（往冥府的安魂歌）`，而 `邪眼` 本身是稻妻词条）。

### 4.1.4 进度（2026-10 更新）
- **aq / eq / legend(lq)**：主体 ✅ 已 BWIKI 校正。
- **wq**：

| 区域 | 蒙德·龙脊雪山·璃月·稻妻·渊下宫 | 须弥·枫丹·纳塔·挪德卡莱·霜月 | 至冬 |
|---|---|---|---|
| 状态 | ✅ BWIKI | ✅ BWIKI | ⬜ BWIKI 待上游（树上 12 叶已用新内核优化为 Yatta 版） |

- **本版本（7.1）增量**：
  - **aq 至冬**：1700 无神怜爱的雪国 / 1701 死魂灵的夜曲（旧）；**1702 白夜似梦初醒 · 1703 往冥府的安魂歌** ✅ BWIKI 校正（各 3 幕全采 BWIKI；「邪眼」幕走备用页）；**10288 异象** ⬜ 暂 Yatta（BWIKI 未更，但内容已较全）。
  - **eq 7.1**（新增 9 叶）：✅ BWIKI 校正 5 个 —— **10289 又是一年明月夜 · 10287 为了拯救美食街！ · 71675 小小藤人驱邪术 · 71676 幡旗除魔战记 · 71677 符箓弹幕万花筒**；⬜ **10259 / 10274 / 10275 / 10276**（诗词四幕）BWIKI 独立页未建 → 暂 Yatta。
  - **wq 至冬**：树上 12 叶（10187 / 10283 / 10255 / 10282 / 10188 / 77148 / 77129 / 77130 / 77132 / 77209 / 77210 / 77211）已用新内核重爬（Yatta 版）。
  - **待排布（暂存 `staging\quest\` 余 11 个）**：10285 · 10286 · 75304 · 75305 · 77664 · 77665 · 77666 · 77667 · 77668 · 77669 · 77688（等版本/活动排布确定后再挂树合并）。
- 曾用的 `tools\correct\_需留意清单.md` 已在收尾删除；`_废弃任务清单.md` 在 `data\trees\`；校正中间产物 `tools\correct\bwiki_data\` 收尾已清（运行时按需重建）。
- aq 存档：蒙德 1001-1003 · 璃月 1101-1104 · 稻妻 1201-1207 · 须弥 1301-1308 · 枫丹 1401-1406 · 纳塔 1500-1506+1004 · 挪德卡莱 1600-1611 · 至冬 1700-1703。

### 4.1.5 硬约束与踩坑（**改解析器前必读**）
- **`<br>` = 换行 / 对话分隔符**：BWIKI 用它分隔同一物理行内的多条对话（尤其折叠里），解析时等同 `\n`。**切勿当排版残留删掉**，否则两条对话会被粘成一条。
- **`{{剧情选项}}` 只能按顶层 `|` 切分**（`split_top_level_params`，忽略嵌套 `{{…}}`/`[[…]]`）。否则内层参数并入外层 → 子树在兄弟选项间重复 → **体积指数级膨胀**。改完务必拿深层嵌套故事验证体积。
- **`{{折叠}}` / `{{折叠框}}`** → 展平成 `===标题===` + 内容并生成 `collapse_ranges`；**只认 `折叠`/`折叠框`，别把 `折叠面板` 扩进来**。
- **`{{注音|文|注}}` / `{{下注音}}` → `文（注）`**：自带 `|`，若位于 `*角色：` 角色位不先转换，会因角色名正则不含 `|` 而**整行丢失**。
- **角色位容错**：角色可含 `{{…}}`/`＜…＞`（如 `库里什＜{{颜色|红|已死亡}}＞：…`），匹配后 `_strip_inline` 去 markup、lstrip 前导 `*`/`:`。
- **`{{人物对话|方位|角色|台词}}` → `角色：台词`**；解析前先剥 `<!-- -->` 注释。
  - ⚠️ **已知未修的坑**：台词内嵌套 `{{颜色}}/{{黑幕}}` 时，内联展开正则（`[^{}]*`）失败 → **静默丢行**，或尾巴 `}}` 泄漏触发校验中止。**对策**：用一次性脚本按 ID 离线重解析（把展开换成 `find_template_end` 配平 + 顶层切分）。
- ⚠️ **任务重名 / 页名≠源名 / 一任务多页 / 同名页是别的东西**：只按名抓可能命中歧义页或无「任务剧情」页。实例：`蒂尔·亚什特的赞歌` 分 `其一/其二`；`先驱`+`先驱·其二`；`追寻·其一/其二`；`最后的特诺奇兹托克人` 的同名页实为**怪物图鉴**（任务页是 `…（世界任务）`）；`执望三千里` 同名页把两任务合在一起。**命中歧义页/无剧情段会回退本地**，需人工取正确页名/页序（看 `前置/后续`、`任务编号`、与本地 story 吻合度），**多 story 按序拼多页**后按 ID 写回。
- **`{{提示}}`/`{{提示消息}}`**：提示框正文转旁白；无 `宽度=`/`<br>`/`<center>`/图片的纯文字提示视为**编辑者备注丢弃**。
- **`{{任务描述|正文|地区}}`**：正文已由 story `description` 承载，**整块丢弃**（否则含 `<br>` 时尾巴泄漏）。
- **旁白统一**：整行旁白（`<font>`/`{{颜色}}`/`{{黑幕}}`/`::文字`/纯文字行）一律输出带 `narration:true` 的 `subtitle`；勿回退成 `{"role":"旁白"}`。
- **跨行构造先折行**：`parse_dialogues_from_section` 先 `_replace_zhuyin` 再 `_collapse_narr_constructs`（把 `{{颜色}}`/`{{黑幕}}`/`{{提示}}`/`{{任务描述}}`/`<font>` 内部的 `\n`、`<br>` 折成哨兵 `\x01`，末尾 `_clean_narr` 还原）。
- **反爬（HTTP 567）是常态**：按 IP 限流，个别故事 `not_found`（→ 回退本地）**不是 bug**；隔时重跑或 `run_ids --force` / `fetch_bwiki_single.py` 补爬。
- **"需留意"清单**：凡没完全用 BWIKI 的故事，`_report_notes` 会**追加**（不覆写）到脚本同目录的 `_需留意清单.md`（现该文件已删，运行时会重建在 `tools\correct\` 下）。**勿改成 `"w"` 覆写**。

### 4.1.6 任务文件格式（travellog）
```json
{
  "quest_id": 1001, "chapter_num": "序章 第一幕", "chapter_title": "捕风的异乡人",
  "type": "aq", "route": "The Outlander Who Caught the Wind",
  "stories": [
    {
      "story_id": 351, "title": "流浪者的足迹", "description": "……",
      "collapse_ranges": [[1, 2]],
      "dialogues": [
        { "role": "派蒙", "text": "……" },
        { "type": "subtitle", "text": "章节小标题" },
        { "type": "choice", "role": "玩家", "options": [ { "text": "选项A", "dialogues": [ { "role": "派蒙", "text": "…" } ] } ] }
      ]
    }
  ]
}
```
- **对话** `{role,text}`；**副标题/旁白** `{type:"subtitle",text}`（旁白带 `narration:true`，仅原文有颜色才带 `color`）；**选择** `{type:"choice",role:"玩家",options:[{text,dialogues:[…]}]}`，可嵌套。
- story 级 `collapse_ranges:[[start,end],…]`：`dialogues` **顶层下标区间**（含端点、可嵌套），代表 `{{折叠}}` 内容；HTML 据此画浅蓝框。⚠️ 只索引顶层，管不到 `choice` 内层。
- `story_id` 可为 `null`（游戏无 id 的段落，如 ID10069 末段）；`generate_html_v2.py` 不读它。
- **未做 BWIKI 校正的故事不产出 `collapse_ranges`**（Yatta 版无折叠）；查看器按 `ranges || []` 容忍缺失。

### 4.1.7 提取内核重写 + 工具集（2026-10）
- **`fetch_quest_update.py` 提取内核重写**（对齐本地 schema）：
  - MultiDialog 分支**递归嵌套**（`options=[{text,dialogues}]`）：先算各分支的合并点(join)，分支独有内容进选项、合并点之后的公共内容才置后。旧版只跟第一个选项、其余分支丢弃。
  - `step.title` → `{type:"subtitle"}`（跳过 `$HIDDEN`/`(test)` 的故事与步骤）。
  - 解析 `#` 行占位符（`{NICKNAME}`/`{M#..}{F#..}`/SEXPRO/RUBY/颜色/图标），`role 旅人→旅行者`；`visited` 防环。
  - `extract_local_ids` 兼容 `..._{id}.json`（无类型后缀）与 `..._{id}_{type}.json`（旧版只认后者，会把已存在的任务误判为新任务反复抓）。
  - 参数：`--dry`（只列新增）/ `--out` / `--limit`。
- **`tools\quest_ops\`（工具集，原「任务更新专项优化」）**：

| 脚本 | 作用 |
|---|---|
| `extract_quest.py` | 单/多任务提取 demo（CLI，输出到 `tools\quest_ops\extracted\`） |
| `replace_tree_node.py` | 按「树 + 节点」批量**原地替换**任务文本（自动备份到 `tools\quest_ops\_backup\{节点}_old\`） |
| `merge_node_from_staging.py` | 校验树节点合法性 + 把 `staging\quest\` 里的任务合并进数据库 |
| `check_resolve.py` | 按查看器规则校验叶子能否命中本地文件（`{名}_{id}_{type}.json`，type 试 aq/wq/eq/iq/lq） |
| `inspect_tree.py` / `count_orphans.py` | 树结构查看 / 未进树（孤儿）统计 |
| `compare.py` / `show_stories.py` / `scan_tpl.py` | 与本地对照 / 打印各 story / 扫残留 BWIKI 模板 |

> **旧任务批量重爬（一次性，已执行）**：把**未进 aq/eq/legend/wq 四树**的 688 个既有任务用新内核重爬并原地替换（test/HIDDEN 跳过），文本质量较旧爬取器提升（分支不再丢、占位符已解析）。

## 4.2 圣遗物（artifact） — ✅ 已完成（仅删除 affix_list）
- **数据**：`data\artifact\`（Ambr 直出）；树 `data\trees\artifact_tree.json`（叶=套装名，`id`=`name`）；HTML 类型 `artifact`。
- **页名规则**：BWIKI 页名 = 套装名，63/63 命中；正文为单个 `{{圣遗物套装}}` 模板（参数按名取值，顺序不固定）。
- **结论**：与 BWIKI 逐套比对，差异极小且**双向都有笔误**（BWIKI 反而更多，如"最高上"、"难民与的安全撤离"、"80点 。"），故**不做 BWIKI 校正**，保留本地 Ambr 文本。
- **已处理**：删除全 63 个文件的 `affix_list` 字段（游戏内效果描述，非主要文本）；story/description 保持原样。
- **代码已同步**：`generate_html_v2.py` 移除「套装效果」渲染；`fetch_artifact_update.py` 不再抓取该字段。
- **状态**：✅ 完成。

## 4.3 书籍（book） — ✅ 已完成
- **数据**：`data\book\`（Ambr 直出）；树 `data\trees\book_tree.json`（**自定义两层**）；HTML 类型 `book`。
- **命名规范**：`{名字}_{id}.json`（id 取 JSON `id`）。全 603 个文件已统一重命名。
- **分类**：JSON `id` **<10000 → 故事书**（74）；**≥10000 → 地图文本**（529）；断层 1076 ↔ 100181（干净，阈值稳）。
- **树结构**：`书籍` → `书籍(74)` + `地图可阅读物(67)`。由 `regenerate_trees.py` 的 `build_book_tree()` **自引导**生成：
  - 故事书**全收**（放进 `data\book\` 即进树）；
  - 地图文本**只保留已存在于现有 `book_tree.json` 的**（要新增就手动加叶子，格式 `{"name","id":"名字_id","type":"book"}`）；
  - **无外部白名单文件**（不依赖 md）。
- **废弃**：`.json`(空名, id 100470)、`(test)提纳里的来信`(id 120260) → 见 `data\trees\_废弃书籍清单.md`（代码里 `BOOK_EXCLUDE`）。
- **爬取**：`fetch_book_update.py` 按 **JSON `id`** 去重（改名/改标题都不会误重爬），输出名 `{名字}_{id}.json`。
- **文本口径**：保留本地 Ambr 文本（未做 BWIKI 比对）。
- **状态**：✅ 完成。工作脚本/记录在 `tools\correct\`（`analyze_books.py` → `书籍分类_故事书vs地图文本.md`）。

## 4.4 角色（character） — ✅ 已完成（全量重爬 7.1）
- **数据**：`data\character\`（Ambr 直出，全量重爬）；树 `data\trees\character_tree.json`；HTML 类型 `character`。
- **更新方式**：**全量重爬**（老角色会随版本新增语音/故事，增量补不到）。脚本 `fetch_character_update.py`：抓全部 → 备份旧数据到 `staging\character\_backup_<ts>\` → 替换本地；**有失败即中止不替换**。
- **字段（精简后）**：`id / name / element / title / constellation / story{title,text} / quotes{title,text}`。
  - 去掉：`cv`、`weapon_type`、`region`、story 的 `title2/text2/tips`、quotes 的 `audio/tips/tasks`。
  - `id` 与本地一致：原始 `c.id`（普通角色纯数字如 `10000035`；旅行者 `10000005-pyro`）。
- **特殊处理**：
  - **旅行者**：14 个元素/性别变体共享故事与语音，脚本**去重只留一个**（输出 `旅行者.json`）；其 fetter 只挂在**裸 id**（`10000005`/`10000007`）上，走原始接口 `avatarFetter/{base}`。
  - **排除**：`奇偶·男性`、`奇偶·女性`（`EXCLUDE_NAMES`）。
- **踩坑**：`avatarFetter/{id}-{element}` 对旅行者返回无数据；裸 id 的 detail 缺 talent/constellation（ambr 模型校验失败）。
- **HTML**：仅用 `name/title/constellation/story/quotes`；**已加防缓存** `?v=时间戳`（否则点开会读到浏览器缓存的旧 JSON）。
- **状态**：✅ 完成。

## 4.5 材料（material） — ✅ 已完成（仅裁剪字段）
- **数据**：`data\material\`；树 `data\trees\material_tree.json`；HTML 类型 `material`。
- **已处理**：820 文件裁剪为四字段（`name/rarity/type/description`）；`fetch_material_update.py` 同步；HTML 去「获取来源/合成配方」；修复 8 个带 id 异常。
- **文本口径**：保留本地 Ambr 文本（未做 BWIKI 比对）。
- **状态**：✅ 完成。

## 4.6 武器（weapon） — ✅ 无需处理
- **结论**：人工确认本地数据（Ambr 直出）已满足需求，不做任何校正/改动，保持现状。
- **状态**：✅ 无需处理。

---

## 5. 查看 HTML
- 运行 `python serve.py`（起本地服务并自动打开 `web/quest_tree.html`）。左侧树导航（任务 4 类 + 圣遗物/书籍/角色/材料/武器 5 类），点叶子右侧渲染；任务含 `{{折叠}}` 的显示**浅蓝框 + 标题**。
- 只改了数据（没动脚本）时，**重启 `serve.py`** 避免缓存即可（查看器另有 `?v=时间戳` 防缓存）。
- HTML 由 `tools\generate_html_v2.py` 生成；其 `QUEST_TREES` 现为 **4 项（aq/eq/legend/wq）**——iq（邀约）已按需求移除，**除非要恢复邀约，别加回**。
- 查看器通过浏览器相对路径现拉 JSON：`../data/quest/`、`../data/artifact/` 等（服务根=仓库根）。
