# -*- coding: utf-8 -*-
r"""run_task.py — 单任务一体化处理脚本
输入: 任务名 + ID（脚本内不读任务树）。
流程: 抓取(BWIKI) -> 备份原版(_yatta) -> 转换 -> 折叠边界 -> 写回 travellog -> 输出完成情况。
不含 HTML 生成（单独用 generate_html_v2.py）。
"""
import json
import sys
import os
import time
import random
import urllib.request
import urllib.parse
import re
import glob
import shutil
import difflib

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
OUTPUT_DIR = str(ROOT / "tools" / "correct" / "bwiki_data")
SOURCE_DIR = str(ROOT / "data" / "quest")

BASE_DELAY = 5.0
MAX_RETRIES = 3
RETRY_DELAY = 60.0
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_ua():
    return random.choice(USER_AGENTS)


def fetch_wikitext(page_name: str) -> tuple:
    """返回 (status, wikitext)，status ∈ {"ok","missing","throttled"}。
    - "missing"：页面确实不存在（API 正常响应、无 parse 字段）→ 确定性结论，调用方可立即跳过、无需重试。
    - "throttled"：反爬(HTTP 567)，重试 MAX_RETRIES 次仍未取到 → 属暂时性，可稍后补爬。
    """
    encoded = urllib.parse.quote(page_name)
    url = f"https://wiki.biligame.com/ys/api.php?action=parse&page={encoded}&prop=wikitext&format=json"

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": get_ua()})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "parse" in data:
                    return ("ok", data["parse"]["wikitext"]["*"])
                return ("missing", None)  # 页面不存在：立即返回，不重试
        except urllib.error.HTTPError as e:
            if e.code == 567:
                if attempt < MAX_RETRIES - 1:  # 最后一次不必再等
                    print("  反爬(567)，等60s...")
                    time.sleep(60.0)
            else:
                time.sleep(BASE_DELAY * 2)
        except Exception:
            time.sleep(BASE_DELAY * 2)
    return ("throttled", None)


def extract_description(wikitext: str) -> str:
    """从 {{任务|...}} 模板中提取任务描述"""
    m = re.search(r"\|任务描述\s*=\s*(.*?)(?:\n\s*\||\n\}\})", wikitext, re.DOTALL)
    if m:
        desc = m.group(1).strip()
        # 去掉注释
        desc = re.sub(r"<!--.*?-->", "", desc)
        return desc.strip()
    return ""


def extract_dialogue_section(wikitext: str) -> str:
    """只提取「任务剧情」部分。多层回退（兼容各种页面写法）：
    1) ==任务剧情== 段；
    2) 无该标题 → 取 {{任务…}} 模板之后、下个二级标题之前；
    3) 既无 ==任务剧情== 也无 {{任务}}（剧情直接写在 ==故事名== 等二级标题下）→ 取第一个二级标题到下一个二级标题之前。"""
    m_start = re.search(r"(?:^|\n)==\s*任务剧情\s*==", wikitext)
    if m_start:
        rest = wikitext[m_start.end():]
        m_end = re.search(r"\n==[^=]", rest)
        return rest[: m_end.start()] if m_end else rest

    # 回退2：对话接在 {{任务…}} 模板之后
    m_task = re.search(r"\{\{任务\b", wikitext)
    if m_task:
        rest = wikitext[find_template_end(wikitext, m_task.start()):]
    else:
        # 回退3：剧情直接写在 ==故事名== 等二级标题下（无 {{任务}} 模板）
        m_sec = re.search(r"(?:^|\n)==[^=][^\n]*==", wikitext)
        if not m_sec:
            return ""
        rest = wikitext[m_sec.end():]
    rest = re.sub(r"^\s*==[^=][^\n]*==\s*\n", "", rest, count=1)  # 去掉紧随的 ==故事名==
    m_end = re.search(r"\n==[^=]", rest)
    return rest[: m_end.start()] if m_end else rest


def find_template_end(text, start):
    """从 start 位置开始，找到与 {{ 匹配的 }} 位置（支持嵌套）"""
    depth = 0
    i = start
    while i < len(text) - 1:
        if text[i:i+2] == "{{":
            depth += 1
            i += 2
        elif text[i:i+2] == "}}":
            depth -= 1
            if depth == 0:
                return i + 2
            i += 2
        else:
            i += 1
    return len(text)


def _is_narration_text(seg: str) -> bool:
    """是否可作为「纯文字旁白」：非标记起始、且至少含一个中文字。"""
    if not seg:
        return False
    if seg.startswith(("{{", "|", "[[", "<", "]", "{|", "*", "#", "!", "=", "-", "'", "_", ",")):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", seg))


_NARR_TAGS = {"small", "big", "center", "div", "em", "i", "b", "strong", "u", "s", "del", "sup", "sub"}


def _clean_narr(txt: str) -> str:
    """清理旁白文本：<br>/\\x01→换行，去 HTML 标签，去 wiki 链接。"""
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.IGNORECASE)
    txt = txt.replace("\x01", "\n")
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", txt)
    txt = re.sub(r"\[\[([^\]]*)\]\]", r"\1", txt)
    return txt.strip()


def _narration_item(s: str):
    """识别旁白构造（可含 ::/* 前缀），返回带 narration 标记的 subtitle，或 None。
    支持：<font color=X>…</font>、其它整行单标签（如 <small>/<center>）、{{颜色|…}}、{{黑幕|…}}。"""
    t = re.sub(r"<br\s*/?>\s*$", "", s.lstrip("*:").strip(), flags=re.IGNORECASE).strip()
    if not t:
        return None
    mf = re.match(r"<font[^>]*>(.*)</font>$", t, re.IGNORECASE | re.DOTALL)
    if mf:
        txt = _clean_narr(mf.group(1))
        if not txt:
            return None
        item = {"type": "subtitle", "text": txt, "narration": True}
        cm = re.search(r"color\s*=\s*['\"]?([#\w]+)", mf.group(0), re.IGNORECASE)
        if cm:
            item["color"] = cm.group(1)
        return item
    # 其它"整行被单个 HTML 标签包裹"的旁白（如 <small><b>…</b></small>）
    mtag = re.match(r"<([a-zA-Z][\w]*)\b[^>]*>(.*)</\1>$", t, re.IGNORECASE | re.DOTALL)
    if mtag and mtag.group(1).lower() in _NARR_TAGS:
        txt = _clean_narr(mtag.group(2))
        if txt:
            return {"type": "subtitle", "text": txt, "narration": True}
    mc = re.match(r"\{\{颜色\|([^|}]+)\|(.*)\}\}$", t, re.DOTALL)
    if mc:
        txt = _clean_narr(mc.group(2))
        if txt:
            return {"type": "subtitle", "text": txt, "narration": True, "color": mc.group(1).strip()}
        return None
    mb = re.match(r"\{\{黑幕\|(.*)\}\}$", t, re.DOTALL)
    if mb:
        txt = _clean_narr(mb.group(1))
        if txt:
            return {"type": "subtitle", "text": txt, "narration": True}
        return None
    return None


def parse_dialogue_lines(raw: str) -> list[dict]:
    """解析 followup 内容：含 *角色：对话 / ===副标题=== / 旁白（<font>/{{颜色}}/{{黑幕}}/纯文字）"""
    dialogues = []
    lines = re.split(r"<br\s*/?>\s*|\n", raw, flags=re.IGNORECASE)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        item = _narration_item(line)
        if item:
            dialogues.append(item)
            continue
        if line.startswith("{{提示"):
            dialogues.extend(_tip_items(line))
            continue
        if line.startswith("*"):
            line = line[1:]
        sm = re.match(r"^=+\s*(.+?)\s*=+$", line)
        if sm:
            dialogues.append({"type": "subtitle", "text": _clean_narr(sm.group(1))})
            continue
        dm = re.match(
            r"(?:\[\[([^\]|】]+?)(?:\|[^\]]+)?\]\]|((?:\{\{[^{}]*\}\}|[^\]|：])+?))[：:](.+)", line
        )
        if dm:
            role = _strip_inline((dm.group(1) or dm.group(2) or "").strip().lstrip("*: ").strip())
            text = dm.group(3).strip()
            if role and text:
                dialogues.append({"role": role, "text": text})
            continue
        # 纯旁白/解读结果（非标记行）→ subtitle（旁白，无颜色）
        if _is_narration_text(line):
            dialogues.append({"type": "subtitle", "text": _strip_inline(line.replace("\x01", "\n")), "narration": True})
    return dialogues


def split_top_level_params(block: str) -> list[str]:
    """按顶层 | 把模板内容切分为参数段，忽略嵌套 {{...}}、[[...]]、{|...|} 内的 |"""
    segments = []
    buf = []
    depth_curly = depth_link = depth_table = 0
    i = 0
    while i < len(block):
        two = block[i:i+2]
        if two == "{{":
            depth_curly += 1
            buf.append(two)
            i += 2
            continue
        if two == "}}":
            depth_curly -= 1
            buf.append(two)
            i += 2
            continue
        if two == "[[":
            depth_link += 1
            buf.append(two)
            i += 2
            continue
        if two == "]]":
            depth_link -= 1
            buf.append(two)
            i += 2
            continue
        if two == "{|":
            depth_table += 1
            buf.append(two)
            i += 2
            continue
        if two == "|}":
            depth_table -= 1
            buf.append(two)
            i += 2
            continue
        if block[i] == "|" and depth_curly == 0 and depth_link == 0 and depth_table == 0:
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(block[i])
        i += 1
    segments.append("".join(buf))
    return segments


def parse_followup_content(raw: str) -> list[dict]:
    """解析followup内容，支持嵌套 {{剧情选项}}"""
    dialogues = []
    pos = 0
    while True:
        # 查找嵌套的 {{剧情选项
        nested_start = raw.find("{{剧情选项", pos)
        if nested_start == -1:
            # 没有更多嵌套choice，解析剩余的普通对话
            dialogues.extend(parse_dialogue_lines(raw[pos:]))
            break
        # 解析嵌套choice之前的普通对话
        dialogues.extend(parse_dialogue_lines(raw[pos:nested_start]))
        # 用大括号计数找到嵌套choice的结束位置
        nested_end = find_template_end(raw, nested_start)
        # 提取嵌套choice内容（去掉外层 {{ 和 }}，保留模板名）
        nested_content = raw[nested_start+2:nested_end-2]
        dialogues.append(parse_choice_block(nested_content))
        pos = nested_end
    return dialogues


def parse_choice_block(block: str) -> dict:
    """解析 {{剧情选项}} 模板内容（block 为 {{ }} 内部原文，含开头的模板名），支持嵌套

    关键：只在顶层按 | 切分参数。嵌套 {{剧情选项}} 内部的 |选项N=/|剧情N=
    处于更深的 {{}} 层级，不会被误并入本层。
    """
    options = []
    followups = {}  # option_index -> [dialogues]

    for seg in split_top_level_params(block):
        m = re.match(r"\s*(选项|剧情)(\d+)\s*=\s*(.*)", seg, re.DOTALL)
        if not m:
            # 模板名（剧情选项）等非参数段，跳过
            continue
        kind, idx, value = m.group(1), int(m.group(2)), m.group(3).strip()
        if kind == "选项":
            if value:
                options.append({"index": idx, "text": value})
        else:
            followups[idx] = parse_followup_content(value)

    sorted_options = sorted(options, key=lambda x: x["index"])
    choice = {
        "type": "choice",
        "role": "玩家",
        "options": [
            {"text": o["text"], "dialogues": followups.get(o["index"], [])}
            for o in sorted_options
        ],
    }
    return choice


def _fold_block(block: str) -> str:
    # 把构造内部的换行/<br> 折成哨兵 \x01（单行化，防止被逐行/逐 <br> 解析切断）；_clean_narr 再还原为 \n。
    block = re.sub(r"<br\s*/?>", "\x01", block, flags=re.IGNORECASE)
    block = block.replace("\n", "\x01")
    block = re.sub(r"(?:\x01\s*){2,}", "\x01", block)
    return block


def _collapse_narr_constructs(text: str) -> str:
    """把旁白构造（{{颜色}}/{{黑幕}}/<font>/<small>/<center>/<del> 等）内部的换行折成单行，
    避免逐行解析时闭合符（}} / </font>）泄漏到正文。不影响 {{剧情选项}}。"""
    while True:
        hit = None
        for m in re.finditer(r"\{\{(?:颜色|黑幕|提示消息|提示|任务描述)\|", text):
            end = find_template_end(text, m.start())
            seg = text[m.start():end]
            if "\n" in seg or re.search(r"<br", seg, re.IGNORECASE):
                hit = (m.start(), end)
                break
        if not hit:
            for m in re.finditer(r"<(font|small|center|del|b|i|em|strong|u|s|sup|sub)\b", text, re.IGNORECASE):
                tag = m.group(1)
                e = re.search(r"</" + tag + r">", text[m.start():], re.IGNORECASE)
                if e:
                    end = m.start() + e.end()
                    seg = text[m.start():end]
                    if "\n" in seg or re.search(r"<br", seg, re.IGNORECASE):
                        hit = (m.start(), end)
                        break
        if not hit:
            break
        text = text[:hit[0]] + _fold_block(text[hit[0]:hit[1]]) + text[hit[1]:]
    return text


def _strip_inline(s: str) -> str:
    """去掉行内标记，只留文字：{{黑幕}}/{{颜色}} 取文字，去 HTML 标签与 [[…]] 链接。"""
    s = re.sub(r"\{\{黑幕\|(.*?)\}\}", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"\{\{颜色\|[^|}]*\|(.*?)\}\}", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = s.replace("''", "")
    return s.strip()


def _replace_zhuyin(text: str) -> str:
    """把 {{注音|文字|注音}} / {{下注音|文字|注音}} 统一转成「文字（注音）」（注音内的 {{黑幕}} 等会先去掉）。
    作为 role 时尤其重要：这些模板含 |，否则整行会因 role 正则不匹配而被丢弃。"""
    while True:
        m = re.search(r"\{\{(?:注音|下注音)\|", text)
        if not m:
            break
        i = m.start()
        end = find_template_end(text, i)
        args = [p.strip() for p in split_top_level_params(text[i + 2:end - 2])][1:]
        if args:
            a = _strip_inline(args[0])
            b = _strip_inline(args[1]) if len(args) > 1 else ""
            rep = f"{a}（{b}）" if b else a
        else:
            rep = ""
        text = text[:i] + rep + text[end:]
    return text


def _extract_tip_content(inner: str) -> str:
    """从 {{提示|…}}/{{提示消息|…}} 的模板体提取正文：去掉颜色、命名参数、图片与 HTML，取最长参数为正文。"""
    parts = [p.strip() for p in split_top_level_params(inner)]
    cands = []
    for p in parts[1:]:
        if not p:
            continue
        if re.match(r"^[A-Za-z\u4e00-\u9fff]{1,6}\s*=", p):
            continue
        cands.append(p)
    if not cands:
        return ""
    content = max(cands, key=len)
    content = re.sub(r"\[\[[Ff]ile:[^\]]*\]\]", "", content)
    txt = re.sub(r"'{2,}", "", _clean_narr(content))
    return txt


def _tip_items(line: str) -> list[dict]:
    """把一行中的 {{提示}}/{{提示消息}} 提示框转成旁白条目（去掉纯标签行如「提示」）。"""
    items = []
    pos = 0
    while True:
        i = line.find("{{提示", pos)
        if i < 0:
            break
        end = find_template_end(line, i)
        inner = line[i + 2:end - 2]
        # 仅保留「游戏内提示框」（带 宽度=/<br>/<center>/图片）；无这些格式的纯文字提示视作编辑者备注丢弃
        if re.search(r"宽度\s*=|width\s*=|<br|<center|\[\[[Ff]ile:", inner, re.IGNORECASE):
            for t in _extract_tip_content(inner).split("\n"):
                t = t.strip()
                if t and t not in ("提示", "提示消息"):
                    items.append({"type": "subtitle", "text": t, "narration": True})
        pos = end
    return items


def parse_dialogues_from_section(section: str) -> list[dict]:
    """从任务剧情部分解析对话，支持 {{剧情选项}} 和 {{折叠}} 模板"""
    section = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    section = _replace_zhuyin(_collapse_narr_constructs(section))
    section = re.sub(r"\{\{人物对话\|[^|{}]*\|([^|{}]*)\|([^{}]*)\}\}", r"\1：\2", section)
    # 第一步：展开 {{折叠}} 模板 / <tabber> 标签 → ===标题=== + 内容
    # 兼容两种写法：{{折叠|标题=...|内容=...}} 与 名后换行、参数逐行的多行形式
    #   1) 检测放宽为「{{折叠 后跟空白或 |」
    #   2) 参数按顶层 | 切分（value 可跨行），复用 split_top_level_params
    def expand_fold(inner: str) -> str:
        params = {}
        for seg in split_top_level_params(inner):
            m = re.match(r"\s*([^=|\[{]+?)\s*=\s*(.*)", seg, re.DOTALL)
            if not m:
                continue
            params[m.group(1).strip()] = m.group(2).strip()
        title = params.get("标题") or "折叠内容"
        fold_content = params.get("内容", "")
        # 提取 <span> 标签内的描述文字（如果有）
        span_match = re.search(r'<span[^>]*>(.*?)</span>', fold_content, re.IGNORECASE | re.DOTALL)
        if span_match:
            desc_text = span_match.group(1).strip()
            fold_content_clean = re.sub(r'<span[^>]*>.*?</span>', '', fold_content, flags=re.IGNORECASE | re.DOTALL).strip()
            if desc_text:
                return f"==={title}===\n{desc_text}\n{fold_content_clean}"
        return f"==={title}===\n{fold_content}"

    # 展开 {{折叠...}} / <tabber>...</tabber> / {{#tag:tabber|...}}，逐个处理直到没有
    def expand_tabber(inner: str) -> str:
        out = []
        for tab in re.split(r"\{\{!\}\}-\{\{!\}\}|\|-\||-\|-", inner):
            tab = tab.strip("\n")
            if "=" not in tab:
                continue
            label, content = tab.split("=", 1)
            out.append(f"==={label.strip()}===\n{content.strip()}")
        return "\n".join(out)

    expanded_section = section
    while True:
        cands = []
        m = re.search(r"\{\{折叠框?(?=[\s|])", expanded_section)
        if m:
            cands.append(("fold", m.start()))
        m = re.search(r"<tabber>", expanded_section)
        if m:
            cands.append(("tabber_tag", m.start()))
        m = re.search(r"\{\{#tag:tabber", expanded_section)
        if m:
            cands.append(("tabber_fn", m.start()))
        if not cands:
            break
        kind, start = min(cands, key=lambda x: x[1])
        if kind == "fold":
            end = find_template_end(expanded_section, start)
            repl = expand_fold(expanded_section[start + 2:end - 2])
        elif kind == "tabber_tag":
            close = re.search(r"</tabber>", expanded_section[start:])
            if close:
                end = start + close.end()
                inner = expanded_section[start + len("<tabber>"):start + close.start()]
            else:
                end = len(expanded_section)
                inner = expanded_section[start + len("<tabber>"):]
            repl = expand_tabber(inner)
        else:  # tabber_fn: {{#tag:tabber|...}}
            end = find_template_end(expanded_section, start)
            inner = expanded_section[start + 2:end - 2]
            if "|" in inner:
                inner = inner.split("|", 1)[1]
            repl = expand_tabber(inner)
        expanded_section = expanded_section[:start] + repl + expanded_section[end:]

    # 第二步：用大括号计数找到所有 {{剧情选项}} 块（支持嵌套）
    choice_ranges = []  # [(start, end), ...]
    i = 0
    while i < len(expanded_section):
        start = expanded_section.find("{{剧情选项", i)
        if start == -1:
            break
        end = find_template_end(expanded_section, start)
        choice_ranges.append((start, end))
        i = end

    # 第三步：按行解析普通对话，记录每行在 expanded_section 中的位置
    dialogues_with_pos = []
    current_pos = 0
    choice_idx = 0

    for line in expanded_section.split("\n"):
        # 计算这行在 expanded_section 中的起始位置
        line_start = expanded_section.find(line, current_pos)
        if line_start == -1:
            line_start = current_pos
        line_end = line_start + len(line)

        # 跳过处于 choice 块内部的行
        while choice_idx < len(choice_ranges) and choice_ranges[choice_idx][1] < line_start:
            choice_idx += 1
        if choice_idx < len(choice_ranges) and choice_ranges[choice_idx][0] <= line_start < choice_ranges[choice_idx][1]:
            current_pos = line_end + 1
            continue

        line_stripped = line.strip()

        # 检测标题（=、==、===…）作为副标题
        m_subtitle = re.match(r"^=+\s*(.+?)\s*=+$", line_stripped)
        if m_subtitle:
            dialogues_with_pos.append({"type": "subtitle", "text": _clean_narr(m_subtitle.group(1)), "_pos": line_start})
            current_pos = line_end + 1
            continue

        # 旁白（可带 ::/* 前缀）：<font…> / {{颜色|…}} / {{黑幕|…}} / ::纯文字
        stripped = line_stripped.lstrip("*:").strip()
        # {{提示}}/{{提示消息}} 提示框 → 正文转旁白
        if stripped.startswith("{{提示"):
            for it in _tip_items(stripped):
                dialogues_with_pos.append(dict(it, _pos=line_start))
            current_pos = line_end + 1
            continue
        # {{任务描述}} 为任务描述（已由 description 字段承载）→ 丢弃，避免含 <br> 时尾巴泄漏
        if stripped.startswith("{{任务描述"):
            current_pos = line_end + 1
            continue
        if stripped.startswith(("<", "{{颜色", "{{黑幕")):
            item = _narration_item(line_stripped)
            if item:
                dialogues_with_pos.append(dict(item, _pos=line_start))
                current_pos = line_end + 1
                continue
        elif line_stripped.startswith("::"):
            body = re.sub(r"<br\s*/?>\s*$", "", line_stripped.lstrip(":").strip(), flags=re.IGNORECASE).strip()
            if _is_narration_text(body):
                dialogues_with_pos.append({"type": "subtitle", "text": body, "narration": True, "_pos": line_start})
                current_pos = line_end + 1
                continue

        # 跳过空行和非对话行
        if not line_stripped:
            current_pos = line_end + 1
            continue
        if re.match(r"^\*?\s*\[\[https?://", line_stripped):
            current_pos = line_end + 1
            continue
        if re.match(r"^::", line_stripped) or line_stripped.startswith("{{颜色") or line_stripped.startswith("*{{颜色"):
            current_pos = line_end + 1
            continue

        # 剥离 <span> HTML 标签
        line_stripped = re.sub(r'<span[^>]*>', '', line_stripped, flags=re.IGNORECASE)
        line_stripped = re.sub(r'</span>', '', line_stripped, flags=re.IGNORECASE)

        # 普通对话行：一行内可能用 <br> 分隔多条对话，逐段解析
        # （BWIKI 折叠内容常把多条对话写在同一个物理行、以 <br> 分隔）
        for seg in re.split(r"<br\s*/?>", line_stripped, flags=re.IGNORECASE):
            seg = seg.strip()
            if not seg:
                continue
            m = re.match(
                r"^\s*\*?\s*(?:(?:\[\[([^\]|】]+?)(?:\|[^\]]+)?\]\]|((?:\{\{[^{}]*\}\}|[^\]|：])+?))[：:](.+))\s*$",
                seg,
            )
            if not m:
                # 非角色行 → 纯旁白（非标记行），如诗句/独白
                if _is_narration_text(seg):
                    dialogues_with_pos.append({"type": "subtitle", "text": _strip_inline(seg.replace("\x01", "\n")), "narration": True, "_pos": line_start})
                continue
            role = _strip_inline((m.group(1) or m.group(2) or "").strip().lstrip("*: ").strip())
            text = m.group(3).strip()
            if text.startswith("{{任务") or text.startswith("{{图标"):
                continue
            if role and text:
                dialogues_with_pos.append({"role": role, "text": text, "_pos": line_start})

        current_pos = line_end + 1

    # 第四步：解析 choice 块
    choices_with_pos = []
    for start, end in choice_ranges:
        content = expanded_section[start+2:end-2]  # 去掉外层 {{ 和 }}，保留模板名
        choice = parse_choice_block(content)
        choices_with_pos.append({"choice": choice, "_pos": start})

    # 第五步：按位置合并 dialogues 和 choices
    all_items = dialogues_with_pos + choices_with_pos
    all_items.sort(key=lambda x: x["_pos"])

    dialogues = []
    for item in all_items:
        if "choice" in item:
            dialogues.append(item["choice"])
        else:
            d = {k: v for k, v in item.items() if k != "_pos"}
            dialogues.append(d)

    return dialogues


def parse_stories_from_section(section: str) -> list[dict]:
    """按 ===章节=== 分割并解析"""
    stories = []
    current_title = ""
    current_lines = []

    for line in section.split("\n"):
        m = re.match(r"^=+\s*(.+?)\s*=+$", line)
        if m:
            if current_title and current_lines:
                text = "\n".join(current_lines)
                dialogues = parse_dialogues_from_section(text)
                stories.append({"title": current_title, "dialogues": dialogues})
            current_title = m.group(1)
            current_lines = []
        else:
            current_lines.append(line)

    if current_title and current_lines:
        text = "\n".join(current_lines)
        dialogues = parse_dialogues_from_section(text)
        stories.append({"title": current_title, "dialogues": dialogues})

    return stories


def process_quest(quest_data: dict):
    quest_id = quest_data["quest_id"]
    chapter_title = quest_data["chapter_title"]

    result = {
        "quest_id": quest_id,
        "chapter_num": quest_data["chapter_num"],
        "chapter_title": chapter_title,
        "type": quest_data["type"],
        "route": quest_data["route"],
        "bwiki_stories": [],
    }
    wikitext_map = {}  # story_title -> 原始 wikitext（用于离线重解析）

    print(f"\n{'='*50}")
    print(f"任务: {chapter_title} (ID:{quest_id})")
    print(f"{'='*50}")
    
    start_time = time.time()
    success_count = 0

    for i, story in enumerate(quest_data["stories"]):
        story_title = story["title"]
        story_id = story["story_id"]
        local_dialogues = story["dialogues"]

        if "(test)" in story_title or "$HIDDEN" in story_title:
            result["bwiki_stories"].append({
                "story_id": story_id,
                "title": story_title,
                "description": story.get("description", ""),
                "status": "skipped",
                "local_dialogues": local_dialogues,
                "bwiki_dialogues": [],
            })
            continue

        print(f"\n--- [{i+1}/{len(quest_data['stories'])}] {story_title} (ID:{story_id}) ---")
        print(f"  本地对话数: {len(local_dialogues)}")

        # 候选页名：本名 → 本名（任务） → 本名（章节名）。后两者用于应对「同名页」陷阱。
        candidates = [story_title, story_title + "（任务）", "%s（%s）" % (story_title, chapter_title)]
        best = None  # (dialogues, description, wikitext, page_name)
        primary_status = "ok"

        def _parse_page(wt):
            sec = extract_dialogue_section(wt)
            dlg = parse_dialogues_from_section(sec) if sec else []
            return dlg, extract_description(wt)

        for _ci, _cand in enumerate(candidates):
            if _ci > 0:
                time.sleep(BASE_DELAY + random.uniform(0, 1))
            _st, _wt = fetch_wikitext(_cand)
            if _st != "ok":
                if _ci == 0:
                    primary_status = _st
                continue
            _dlg, _desc = _parse_page(_wt)
            if best is None or len(_dlg) > len(best[0]):
                best = (_dlg, _desc, _wt, _cand)
            # 主名已够用（有剧情且不显著偏小）→ 无需再试备用页
            if _ci == 0 and _dlg and (not local_dialogues or len(_dlg) >= len(local_dialogues) * 0.7):
                break

        if best is None:
            st = "not_found" if primary_status == "missing" else "throttled"
            if st == "not_found":
                print("  BWIKI: 页面不存在（缺页）→ 保留本地，跳过")
            else:
                print("  BWIKI: 反爬(567)未取到 → 保留本地（可稍后补爬）")
            result["bwiki_stories"].append({
                "story_id": story_id,
                "title": story_title,
                "description": story.get("description", ""),
                "status": st,
                "local_dialogues": local_dialogues,
                "bwiki_dialogues": [],
            })
            continue

        bwiki_dialogues, description, wikitext, page_used = best
        wikitext_map[story_title] = wikitext  # 记录原始 wikitext
        if page_used != story_title:
            print(f"  [页名] 采用备用页: {page_used}")
        print(f"  BWIKI对话数: {len(bwiki_dialogues)}")
        if description:
            print(f"  Description: {description[:50]}...")

        result["bwiki_stories"].append({
            "story_id": story_id,
            "title": story_title,
            "description": description,
            "status": "fetched",
            "local_dialogues": local_dialogues,
            "bwiki_dialogues": bwiki_dialogues,
        })

        success_count += 1
        if success_count % 5 == 0:
            print(f"\n  已成功爬取 {success_count} 个任务，暂停30秒...")
            time.sleep(30)

    total_time = time.time() - start_time
    print(f"\n爬取完成，总耗时: {total_time:.1f}秒")
    return result, wikitext_map


S = "\u300eC\u300f"
E = "\u300e/C\u300f"


def convert_bwiki_to_local(bwiki_data: dict) -> dict:
    """将BWIKI格式转换为本地格式"""
    result = {
        "quest_id": bwiki_data["quest_id"],
        "chapter_num": bwiki_data["chapter_num"],
        "chapter_title": bwiki_data["chapter_title"],
        "type": bwiki_data["type"],
        "route": bwiki_data["route"],
        "stories": []
    }

    for bstory in bwiki_data.get("bwiki_stories", []):
        # 选 BWIKI 还是本地(Yatta)：BWIKI 为空、或显著偏小（< 本地 70%）→ 用本地
        bwiki_dlg = bstory.get("bwiki_dialogues", [])
        local_dlg = bstory.get("local_dialogues", [])
        use_local = (not bwiki_dlg) or (bool(local_dlg) and len(bwiki_dlg) < len(local_dlg) * 0.7)
        dialogues = local_dlg if use_local else bwiki_dlg
        story = {
            "story_id": bstory["story_id"],
            "title": bstory["title"],
            "description": bstory.get("description", ""),
            "dialogues": dialogues
        }
        result["stories"].append(story)

    return result


def _fold_params(body: str) -> dict:
    params = {}
    for seg in split_top_level_params(body):
        m = re.match(r"\s*([^=|\[{]+?)\s*=\s*(.*)", seg, re.DOTALL)
        if m:
            params[m.group(1).strip()] = m.group(2).strip()
    return params


def parse_with_collapse(section: str):
    """返回 (items, ranges)：items 为顶层条目（与 parse_dialogues_from_section 同构），
    ranges 为 {{折叠}} 的顶层下标区间 [(start, end), ...]（含端点、按出现顺序）。"""
    s = section
    while True:
        m = re.search(r"\{\{折叠框?[\s|]", s)
        if not m:
            break
        end = find_template_end(s, m.start())
        p = _fold_params(s[m.start() + 2:end - 2])
        title = p.get("标题") or "折叠内容"
        content = p.get("内容", "")
        s = s[:m.start()] + f"\n====={S}{title}=====\n{content}\n====={E}=====\n" + s[end:]

    items = parse_dialogues_from_section(s)
    ranges, keep, stack = [], [], []
    for it in items:
        if isinstance(it, dict) and it.get("type") == "subtitle":
            t = it.get("text", "")
            if t.startswith(S):
                stack.append(len(keep))
                keep.append({"type": "subtitle", "text": t[len(S):]})
                continue
            if t == E:
                if stack:
                    ranges.append((stack.pop(), len(keep) - 1))
                continue
        keep.append(it)
    return keep, ranges


def top_keys(dd) -> list:
    k = []
    for x in dd:
        if not isinstance(x, dict):
            continue
        if x.get("type") == "choice":
            k.append("CH")
        elif x.get("type") == "subtitle":
            k.append("ST:" + str(x.get("text", "")))
        else:
            k.append("D:" + str(x.get("role", "")) + "\x1f" + str(x.get("text", "")))
    return k


def align_map(raw_keys, cur_keys):
    sm = difflib.SequenceMatcher(None, raw_keys, cur_keys, autojunk=False)
    mp = {}
    for a, b, size in sm.get_matching_blocks():
        for t in range(size):
            mp[a + t] = b + t
    return mp, sm.ratio()


def map_index(mp, r, n_raw, n_cur):
    if r in mp:
        return mp[r]
    for d in range(1, n_raw + 1):
        if r - d in mp:
            return min(mp[r - d] + d, n_cur - 1)
        if r + d in mp:
            return max(mp[r + d] - d, 0)
    return None


def preview(items, c0, c1, limit=3):
    out = []
    for x in items[max(0, c0):min(len(items), c1 + 1)][:limit]:
        if x.get("type") == "choice":
            out.append("[choice " + str(x.get("role", "")) + "]")
        elif x.get("type") == "subtitle":
            out.append("\u3010" + str(x.get("text", "")) + "\u3011")
        else:
            out.append("[" + str(x.get("role", "")) + "] " + str(x.get("text", "")))
    return " / ".join(out)




_ROLE_MAP = {"玩家": "旅行者", "空/荧": "空", "荧/空": "荧"}
_TEXT_MAP = [("他/她", "他"), ("他们/她们", "他们"), ("哥哥/姐姐", "哥哥")]


def _simplify_text(s):
    for a, b in _TEXT_MAP:
        s = s.replace(a, b)
    return s


def _simplify(obj):
    """simpler 特有：role 做等价替换；所有 text 做子串替换（递归覆盖 choice/旁白/选项）。"""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "role" and isinstance(v, str):
                obj[k] = _ROLE_MAP.get(v, v)
            elif k == "text" and isinstance(v, str):
                obj[k] = _simplify_text(v)
            else:
                _simplify(v)
    elif isinstance(obj, list):
        for x in obj:
            _simplify(x)


def _check_anomaly(local, result):
    """返回 (hard, notes)：hard=致命异常（中止不写回）；notes=需留意但可继续（用本地/空任务）。"""
    hard, notes = [], []
    for s in local["stories"]:
        if len(s["dialogues"]) == 0:
            notes.append("空任务《%s》（连本地也无文本）" % s["title"])
        nb = len(json.dumps(s["dialogues"], ensure_ascii=False).encode("utf-8"))
        if nb > 500 * 1024:
            hard.append("故事《%s》字节 %d（>500KB，疑似膨胀）" % (s["title"], nb))
    o = []

    def walk(dd):
        for x in dd:
            if isinstance(x, dict) and x.get("type") == "choice":
                for op in x.get("options", []) or []:
                    if isinstance(op, dict):
                        walk(op.get("dialogues", []))
            elif isinstance(x, dict):
                o.append(str(x.get("role", "")) + str(x.get("text", "")))

    for s in local["stories"]:
        walk(s["dialogues"])
    resid = sum(1 for t in o if t.count("}}") > t.count("{{"))
    if resid:
        hard.append("残留 }} 共 %d 处（模板泄漏）" % resid)
    for b in result.get("bwiki_stories", []):
        bw = b.get("bwiki_dialogues", []) or []
        yt = b.get("local_dialogues", []) or []
        if not bw:
            if b.get("status") == "throttled":
                notes.append("【反爬567未取到】《%s》→ 用本地数据（稍后可补爬）" % b.get("title"))
            else:
                notes.append("BWIKI 缺内容《%s》(status=%s) → 用本地数据" % (b.get("title"), b.get("status")))
        elif yt and len(bw) < len(yt) * 0.7:
            notes.append("BWIKI 偏小《%s》(bwiki %d / yatta %d) → 用本地数据" % (b.get("title"), len(bw), len(yt)))
    return hard, notes


def _process_one(name, qid, force):
    """处理单个任务。返回 ('ok'|'skip'|'anomaly'|'error', 说明)。"""
    cands = glob.glob(os.path.join(SOURCE_DIR, "*_%s_*.json" % qid))
    if not cands:
        print("  [error] 源里找不到 ID=%s 的文件" % qid)
        return ("error", "找不到文件", [])
    if len(cands) > 1:
        print("  [error] ID=%s 匹配到多个文件：%s" % (qid, [os.path.basename(c) for c in cands]))
        return ("error", "多匹配", [])
    tlp = cands[0]
    fname = os.path.basename(tlp)
    print("目标文件: %s" % fname)

    quest_data = json.load(open(tlp, encoding="utf-8"))
    quest_id = quest_data["quest_id"]
    chapter_title = quest_data["chapter_title"]
    task_dir = os.path.join(OUTPUT_DIR, "%s_%s" % (chapter_title, quest_id))
    existing_bwiki = os.path.join(task_dir, fname.replace(".json", "_bwiki.json"))
    if os.path.exists(existing_bwiki) and not force:
        print("  [skip] 已处理过（%s）" % existing_bwiki)
        return ("skip", "已处理", [])
    os.makedirs(task_dir, exist_ok=True)

    yatta_path = os.path.join(task_dir, fname.replace(".json", "_yatta.json"))
    shutil.copy2(tlp, yatta_path)

    result, wikitext_map = process_quest(quest_data)
    bwiki_path = os.path.join(task_dir, fname.replace(".json", "_bwiki.json"))
    wt_path = os.path.join(task_dir, fname.replace(".json", "_wikitext.json"))
    with open(bwiki_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(wt_path, "w", encoding="utf-8") as f:
        json.dump(wikitext_map, f, ensure_ascii=False, indent=2)

    local = convert_bwiki_to_local(result)
    _simplify(local)  # ← simpler 特有多这一步

    n_bound = 0
    for story in local["stories"]:
        w = wikitext_map.get(story["title"])
        if not w:
            continue
        sec = extract_dialogue_section(w)
        if not sec:
            continue
        raw_items, ranges = parse_with_collapse(sec)
        if not ranges:
            continue
        mp, _ = align_map(top_keys(raw_items), top_keys(story["dialogues"]))
        mapped = []
        for r0, r1 in ranges:
            c0 = map_index(mp, r0, len(raw_items), len(story["dialogues"]))
            c1 = map_index(mp, r1, len(raw_items), len(story["dialogues"]))
            if c0 is not None and c1 is not None and c1 >= c0:
                mapped.append([c0, c1])
        if mapped:
            story["collapse_ranges"] = sorted(mapped)
            n_bound += len(mapped)

    hard, notes = _check_anomaly(local, result)
    if hard:
        print("\n  !! 校验异常，已中止且【不写回】：")
        for x in hard:
            print("     -", x)
        return ("anomaly", "; ".join(hard), notes)

    with open(tlp, "w", encoding="utf-8") as f:
        json.dump(local, f, ensure_ascii=False, indent=2)

    for x in notes:
        print("  [note]", x)
    print("  完成: %s (ID:%s) 故事%d 折叠%d" % (fname, quest_id, len(local["stories"]), n_bound))
    return ("ok", "", notes)


def _report_notes(notes, block=None):
    """打印并【追加】到 校正\\_需留意清单.md（不覆写；已存在的块不动，保住人工勾选）。"""
    print("\n===== 需人工留意（用了本地数据 / 空任务）=====")
    if not notes:
        print("（无）")
        return
    for x in notes:
        print("  -", x)
    try:
        md = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_需留意清单.md")
        existing = open(md, encoding="utf-8").read() if os.path.exists(md) else ""
        title = "## %s" % (block or "未分块")
        if title in existing:
            print("（%s 已存在于 _需留意清单.md，未改动）" % title)
            return
        head = "" if existing else "# 活动任务 · 需人工校正清单\n\n> 勾选表示已处理。机器只追加新块，不覆写。\n\n"
        with open(md, "a", encoding="utf-8") as f:
            f.write(head + title + "\n" + "\n".join("- [ ] " + x for x in notes) + "\n\n")
        print("（已追加 %s 到 _需留意清单.md）" % title)
    except Exception:
        pass


def _resolve_tree(tree_name):
    """tree_name 可为短名（eq/aq/iq/wq/legend，lq=legend）或直接的 .json 路径。"""
    if tree_name and (("\\" in tree_name) or ("/" in tree_name) or tree_name.lower().endswith(".json")):
        return tree_name
    alias = {"lq": "legend"}
    base = alias.get((tree_name or "eq").lower(), (tree_name or "eq").lower())
    return os.path.join(str(ROOT / "data" / "trees"),
                        "%s_quest_tree.json" % base)


def _collect_leaves(node):
    """收集节点下所有叶子任务 (名, id)，按 ID 去重。"""
    leaves = []

    def collect(n):
        if n.get("id") and not (n.get("children") or []):
            leaves.append((re.sub(r"\s*\(ID:\d+\)\s*$", "", n.get("name", "")), n["id"]))
        for c in n.get("children", []) or []:
            collect(c)

    collect(node)
    seen, uniq = set(), []
    for nm, id_ in leaves:
        if id_ in seen:
            continue
        seen.add(id_)
        uniq.append((nm, id_))
    return uniq


def _run_batch(block, force, dry, tree_name="eq"):
    """批量按树处理。eq 树按「版本」分批（原行为不变）；其它树（无版本层）按顶层组分批。"""
    tree_path = _resolve_tree(tree_name)
    tree = json.load(open(tree_path, encoding="utf-8"))
    per_version = tree_path.lower().endswith("eq_quest_tree.json")
    total = 0
    all_notes = []
    for vb in tree.get("children", []):
        vbn = vb.get("name", "")
        if block and block not in vbn:
            continue
        units = (vb.get("children", []) or []) if per_version else [vb]
        for ver in units:
            uniq = _collect_leaves(ver)
            if not uniq:
                continue
            if per_version:
                print("\n######## %s / 版本 %s（%d 个任务）########" % (vbn, ver.get("name"), len(uniq)))
            else:
                print("\n######## %s（%d 个任务）########" % (vbn, len(uniq)))
            for nm, id_ in uniq:
                print(" - %s (ID:%s)" % (nm, id_))
                if dry:
                    total += 1
                    continue
                st, msg, notes = _process_one(nm, id_, force)
                total += 1
                for x in notes:
                    all_notes.append("%s (ID:%s): %s" % (nm, id_, x))
                if st == "anomaly":
                    print("\n⛔ 校验异常，【批量中止】于：%s (ID:%s) —— %s" % (nm, id_, msg))
                    print("   本次已处理 %d 个；请检查后决定是否继续。" % total)
                    _report_notes(all_notes, block)
                    return
            if not dry:
                if per_version:
                    print("== 版本 %s 完成，停 15 秒防反爬 ==" % ver.get("name"))
                else:
                    print("== %s 完成，停 15 秒防反爬 ==" % vbn)
                time.sleep(15)
    print("\n批量结束，共 %d 个任务。" % total)
    _report_notes(all_notes, block)


def main():
    raw = sys.argv[1:]
    force = "--force" in raw
    batch = "--batch" in raw
    dry = "--dry" in raw
    block = None
    tree_name = "eq"
    for a in raw:
        if a.startswith("--block="):
            block = a.split("=", 1)[1]
        elif a.startswith("--tree="):
            tree_name = a.split("=", 1)[1]
    args = [a for a in raw if not a.startswith("--")]

    if batch:
        _run_batch(block, force, dry, tree_name)
        return
    if len(args) < 2:
        print(r'用法: python 校正\run_task_simpler.py "任务名" ID [--force]')
        print(r'      python 校正\run_task_simpler.py --batch [--tree=eq] [--block=1.0-1.6] [--force] [--dry]')
        print(r'      --tree 可为短名 eq/lq/wq/iq/legend，或直接给 .json 路径（默认 eq）')
        return
    _process_one(args[0], args[1], force)


if __name__ == "__main__":
    main()
