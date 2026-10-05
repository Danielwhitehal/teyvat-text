# -*- coding: utf-8 -*-
"""
Generate quest_tree.html with dynamic tree loading from JSON files.
Usage: python generate_html.py
Output: web/quest_tree.html
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
BASE = str(ROOT)
TREE_DIR = os.path.join(BASE, "data", "trees")
OUTPUT = os.path.join(BASE, "web", "quest_tree.html")

# Quest tree files (nested structure)
QUEST_TREES = [
    ("aq_quest_tree.json", "魔神任务"),
    ("eq_quest_tree.json", "活动任务"),
    ("legend_quest_tree.json", "传说任务"),
    ("wq_quest_tree.json", "世界任务"),
]

# Flat tree files (simple list)
FLAT_TREES = [
    ("artifact_tree.json", "圣遗物"),
    ("book_tree.json", "书籍"),
    ("character_tree.json", "角色"),
    ("material_tree.json", "材料"),
    ("weapon_tree.json", "武器"),
]


def add_quest_type(node):
    """只把【带 id 的叶子】标为可点击任务；无 children 又无 id 的当普通标签（不可点）。"""
    if "children" in node and node["children"]:
        for child in node["children"]:
            add_quest_type(child)
    elif node.get("id"):
        node["type"] = "quest"


def load_quest_trees():
    """Load all quest trees and merge into one combined tree."""
    combined = {"name": "任务", "children": []}
    for filename, label in QUEST_TREES:
        path = os.path.join(TREE_DIR, filename)
        if not os.path.exists(path):
            print(f"  SKIP: {filename} not found")
            continue
        with open(path, "r", encoding="utf-8") as f:
            tree = json.load(f)
        add_quest_type(tree)
        combined["children"].append(tree)
    return combined


def load_flat_trees():
    """Load all flat (non-quest) trees."""
    trees = []
    for filename, label in FLAT_TREES:
        path = os.path.join(TREE_DIR, filename)
        if not os.path.exists(path):
            print(f"  SKIP: {filename} not found")
            continue
        with open(path, "r", encoding="utf-8") as f:
            tree = json.load(f)
        trees.append(tree)
    return trees


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>原神任务、圣遗物、书籍、角色、材料及武器树形图</title>
    <style>
        body { font-family: 'Microsoft YaHei', sans-serif; margin: 20px; background: #f5f5f5; }
        .container { display: flex; max-width: 1400px; margin: auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .tree { width: 30%; border-right: 1px solid #ccc; padding: 20px; overflow-y: auto; max-height: 90vh; }
        .detail { width: 70%; padding: 20px; overflow-y: auto; max-height: 90vh; }
        ul { list-style: none; padding-left: 20px; }
        li { margin: 8px 0; }
        details { margin-left: 10px; }
        summary { cursor: pointer; font-weight: bold; color: #2c3e50; }
        a { text-decoration: none; color: #2980b9; cursor: pointer; }
        a:hover { text-decoration: underline; }
        .dialogue { white-space: pre-wrap; font-family: monospace; background: #f9f9f9; padding: 10px; border-radius: 4px; }
        .loading { color: #888; }
        .error { color: red; }
        .piece { margin-bottom: 20px; border-bottom: 1px solid #eee; }
        .volume { margin-bottom: 20px; }
        .volume-title { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
        .full-text { white-space: pre-wrap; line-height: 1.6; }
        .story-section { margin-bottom: 20px; border-left: 3px solid #2980b9; padding-left: 15px; }
        .quote-section { margin-bottom: 20px; }
        .material-section { margin-bottom: 20px; }
        .weapon-section { margin-bottom: 20px; }
        .nickname { 
            color: #FFD700; 
            font-weight: bold;
            text-shadow: 0 0 5px rgba(255,215,0,0.5);
        }
        .dialogue-line { margin: 4px 0; }
        .role-name { color: #2980b9; font-weight: bold; }
        .collapse-box { margin: 8px 0; padding: 6px 12px 6px 12px; border: 1px solid #cfe3f5; border-left: 4px solid #7fb3e0; border-radius: 4px; background: #f6fbff; }
        .collapse-title { font-weight: bold; color: #2c6fa8; margin: 2px 0 6px 0; }
    </style>
</head>
<body>
<div class="container">
    <div class="tree">
        <h2>导航</h2>
        <div id="treeRoot">加载中...</div>
    </div>
    <div class="detail">
        <h2>详细内容</h2>
        <div id="contentDisplay" class="dialogue">点击左侧条目查看详情</div>
    </div>
</div>

<script>
const TREE_DATA = __TREE_DATA_PLACEHOLDER__;

const QUEST_BASE = '../data/quest/';
const ARTIFACT_BASE = '../data/artifact/';
const BOOK_BASE = '../data/book/';
const CHARACTER_BASE = '../data/character/';
const MATERIAL_BASE = '../data/material/';
const WEAPON_BASE = '../data/weapon/';

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function formatGameText(text) {
    if (!text) return '';
    // 先处理未转义的HTML标签（escapeHtml之前）
    text = text.replace(/<span style="color:#[A-Fa-f0-9]+">/g, '');
    text = text.replace(/<\/span>/g, '');
    let result = escapeHtml(text);
    // {{颜色|蓝|文字}} → 文字
    result = result.replace(/\{\{颜色\|[^|}]+\|([^}]+)\}\}/g, '$1');
    // {{黑幕|文字}} → 文字
    result = result.replace(/\{\{黑幕\|([^}]+)\}\}/g, '$1');
    // {{注音|文字|注音}} → 文字（注音）
    result = result.replace(/\{\{注音\|([^|}]+)\|([^}]+)\}\}/g, '$1（$2）');
    // <color=#RRGGBB>文字</color> → 文字
    result = result.replace(/&lt;color=#[A-Fa-f0-9]+&gt;/g, '');
    result = result.replace(/&lt;\/color&gt;/g, '');
    // {NICKNAME} → 旅行者
    result = result.replace(/\{NICKNAME\}/g, '旅行者');
    // #开头的选项文本（去掉#）
    result = result.replace(/^#/, '');
    // 换行符 → <br>（旁白/对话文本内的换行）
    result = result.replace(/\n/g, '<br>');
    return result;
}

function narrationColor(c) {
    var s = String(c).toLowerCase();
    if (s === '灰' || s === 'gray' || s === 'grey') return '#888888';
    if (/^#?[0-9a-f]{6}$/.test(s)) return s.charAt(0) === '#' ? s : '#' + s;
    return '#CCB991';
}

// 递归渲染对话（支持嵌套choice）
function renderDialogue(dlg, indent) {
    indent = indent || 0;
    let html = '';
    let ml = (indent * 20) + 'px';
    let ml2 = ((indent + 1) * 20) + 'px';
    if (dlg.type === 'choice') {
        html += '<div class="dialogue-line" style="margin-left:' + ml + ';"><span class="role-name">[' + escapeHtml(dlg.role) + ']</span> 选项：</div>';
        for (const opt of dlg.options) {
            const optText = typeof opt === 'string' ? opt : opt.text;
            const optDialogues = (typeof opt === 'object' && opt.dialogues) ? opt.dialogues : [];
            html += '<div class="dialogue-line" style="margin-left:' + ml2 + ';">- ' + formatGameText(optText) + '</div>';
            for (const fd of optDialogues) {
                html += renderDialogue(fd, indent + 2);
            }
        }
    } else if (dlg.type === 'subtitle') {
        var subColor = '#2c3e50';
        if (dlg.color) { subColor = narrationColor(dlg.color); }
        html += '<div class="subtitle-line" style="font-weight:bold; margin:10px 0; color:' + subColor + '; margin-left:' + ml + ';">' + formatGameText(dlg.text) + '</div>';
    } else {
        html += '<div class="dialogue-line" style="margin-left:' + ml + ';"><span class="role-name">[' + escapeHtml(dlg.role) + ']</span> ' + formatGameText(dlg.text) + '</div>';
    }
    return html;
}

// 按「折叠区间」渲染：ranges 为 [[start,end],...]（含端点，可嵌套），无则等同逐条渲染
function renderDialogueRange(dialogues, ranges, lo, hi, indent) {
    let html = '';
    let i = lo;
    while (i <= hi) {
        let rng = null;
        for (const r of (ranges || [])) { if (r[0] === i && r[1] <= hi) { rng = r; break; } }
        if (rng) {
            const title = dialogues[i] ? (dialogues[i].text || '') : '';
            html += '<div class="collapse-box"><div class="collapse-title">' + formatGameText(title) + '</div>';
            html += renderDialogueRange(dialogues, ranges, i + 1, rng[1], indent);
            html += '</div>';
            i = rng[1] + 1;
        } else {
            html += renderDialogue(dialogues[i], indent);
            i++;
        }
    }
    return html;
}

function buildTree(node, depth) {
    const el = document.createElement('details');
    // Only open the first 2 levels by default, collapse deeper levels
    el.open = (depth < 2);
    const summary = document.createElement('summary');
    summary.textContent = node.name;
    el.appendChild(summary);

    if (node.children && node.children.length > 0) {
        const ul = document.createElement('ul');
        for (const child of node.children) {
            const li = document.createElement('li');
            if (child.children && child.children.length > 0) {
                li.appendChild(buildTree(child, depth + 1));
            } else {
                // Leaf node
                const a = document.createElement('a');
                a.href = '#';
                // Show name without duplicate ID for quests (name already contains ID)
                const displayName = child.type === 'quest' ? child.name.replace(/\s*\(ID:\d+\)\s*$/, '') : child.name;
                a.textContent = displayName;
                const type = child.type || '';
                if (type === 'quest') {
                    // Quest: find the filename from travellog_json
                    a.onclick = function(e) {
                        e.preventDefault();
                        showQuestById(child.id, child.name);
                    };
                } else if (type === 'artifact') {
                    a.onclick = function(e) {
                        e.preventDefault();
                        showArtifactDetail(child.id, child.name);
                    };
                } else if (type === 'book') {
                    a.onclick = function(e) {
                        e.preventDefault();
                        showBookDetail(child.id, child.name);
                    };
                } else if (type === 'character') {
                    a.onclick = function(e) {
                        e.preventDefault();
                        showCharacterDetail(child.id, child.name);
                    };
                } else if (type === 'material') {
                    a.onclick = function(e) {
                        e.preventDefault();
                        showMaterialDetail(child.id, child.name);
                    };
                } else if (type === 'weapon') {
                    a.onclick = function(e) {
                        e.preventDefault();
                        showWeaponDetail(child.id, child.name);
                    };
                } else {
                    a.onclick = function(e) { e.preventDefault(); };
                }
                li.appendChild(a);
            }
            ul.appendChild(li);
        }
        el.appendChild(ul);
    }
    return el;
}

function initTree() {
    const root = document.getElementById('treeRoot');
    root.innerHTML = '';
    root.appendChild(buildTree(TREE_DATA, 0));
}

// === Quest loading ===
async function showQuestById(questId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';

    // Strip "(ID:xxx)" suffix from name if present
    const cleanName = name.replace(/\s*\(ID:\d+\)\s*$/, '');

    try {
        const types = ['aq', 'wq', 'eq', 'iq', 'lq'];
        let data = null;
        const cacheBust = '?v=' + Date.now();
        for (const t of types) {
            const filename = cleanName + '_' + questId + '_' + t + '.json';
            try {
                const resp = await fetch(QUEST_BASE + filename + cacheBust);
                if (resp.ok) {
                    data = await resp.json();
                    break;
                }
            } catch(e) {}
        }
        if (!data) {
            displayDiv.innerHTML = '<div class="error">未找到任务文件: ' + escapeHtml(name) + '</div>';
            return;
        }
        let html = '<h3>' + escapeHtml(name) + '</h3>';
        for (const story of data.stories || []) {
            html += '<div class="story-section">';
            if (story.title) html += '<h4>【' + escapeHtml(story.title) + '】</h4>';
            if (story.description) html += '<p><em>' + formatGameText(story.description) + '</em></p>';
            const _dlgs = story.dialogues || [];
            html += renderDialogueRange(_dlgs, story.collapse_ranges, 0, _dlgs.length - 1, 0);
            html += '</div>';
        }
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

// 递归渲染对话为纯文本（支持嵌套choice）
function renderDialogueText(dlg, indent) {
    indent = indent || 0;
    let text = '';
    let prefix = '  '.repeat(indent);
    if (dlg.type === 'choice') {
        text += prefix + '[' + dlg.role + '] 选项：\n';
        for (const opt of dlg.options) {
            const optText = typeof opt === 'string' ? opt : opt.text;
            const optDialogues = (typeof opt === 'object' && opt.dialogues) ? opt.dialogues : [];
            text += prefix + '  - ' + optText + '\n';
            for (const fd of optDialogues) {
                text += renderDialogueText(fd, indent + 2);
            }
        }
    } else if (dlg.type === 'subtitle') {
        text += prefix + '【' + dlg.text + '】\n';
    } else {
        text += prefix + '[' + dlg.role + '] ' + dlg.text + '\n';
    }
    return text;
}

// 纯文本版：折叠区间用 ┌─/└─ 框起来
function renderDialogueRangeText(dialogues, ranges, lo, hi, indent) {
    let text = '';
    let i = lo;
    while (i <= hi) {
        let rng = null;
        for (const r of (ranges || [])) { if (r[0] === i && r[1] <= hi) { rng = r; break; } }
        if (rng) {
            const title = dialogues[i] ? (dialogues[i].text || '') : '';
            text += '  '.repeat(indent) + '┌─ ' + title + '\n';
            text += renderDialogueRangeText(dialogues, ranges, i + 1, rng[1], indent + 1);
            text += '  '.repeat(indent) + '└─\n';
            i = rng[1] + 1;
        } else {
            text += renderDialogueText(dialogues[i], indent);
            i++;
        }
    }
    return text;
}

async function showDetail(id, name, filename) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    if (!filename) {
        displayDiv.innerHTML = '<div class="error">未找到对应的 JSON 文件</div>';
        return;
    }
    const url = QUEST_BASE + filename + '?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let text = '';
        for (const story of data.stories || []) {
            if (story.title) text += '\n【' + story.title + '】\n';
            if (story.description) text += '（' + story.description + '）\n';
            const _dlgs = story.dialogues || [];
            text += renderDialogueRangeText(_dlgs, story.collapse_ranges, 0, _dlgs.length - 1, 0);
            text += '\n';
        }
        displayDiv.innerHTML = '<h3>' + escapeHtml(name) + '</h3><pre>' + escapeHtml(text) + '</pre>';
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

async function showArtifactDetail(artifactId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    const url = ARTIFACT_BASE + artifactId + '.json?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let html = '<h2>' + escapeHtml(data.name) + '</h2>';
        if (data.pieces && data.pieces.length) {
            html += '<h3>各部位故事</h3>';
            for (const piece of data.pieces) {
                html += '<div class="piece">';
                html += '<h4>' + escapeHtml(piece.slot) + '：' + escapeHtml(piece.name) + '</h4>';
                if (piece.description) html += '<p><strong>描述：</strong>' + escapeHtml(piece.description) + '</p>';
                if (piece.story) html += '<p><strong>故事：</strong><br>' + escapeHtml(piece.story).replace(/\n/g, '<br>') + '</p>';
                html += '</div>';
            }
        }
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

async function showBookDetail(bookId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    const url = BOOK_BASE + bookId + '.json?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let html = '<h2>' + escapeHtml(data.name) + '</h2>';
        if (data.volumes && data.volumes.length) {
            for (const vol of data.volumes) {
                html += '<div class="volume">';
                html += '<div class="volume-title">' + escapeHtml(vol.volume_name) + '</div>';
                if (vol.description) html += '<p><em>' + escapeHtml(vol.description) + '</em></p>';
                if (vol.full_text) html += '<div class="full-text">' + escapeHtml(vol.full_text).replace(/\n/g, '<br>') + '</div>';
                html += '</div>';
            }
        }
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

async function showCharacterDetail(characterId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    const url = CHARACTER_BASE + characterId + '.json?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let html = '<h2>' + escapeHtml(data.name) + '</h2>';
        if (data.title) html += '<p><strong>称号：</strong>' + escapeHtml(data.title) + '</p>';
        if (data.constellation) html += '<p><strong>命之座：</strong>' + escapeHtml(data.constellation) + '</p>';
        if (data.story) {
            html += '<h3>角色故事</h3>';
            for (const [key, story] of Object.entries(data.story)) {
                html += '<div class="story-section">';
                html += '<h4>' + escapeHtml(story.title || '故事' + key) + '</h4>';
                if (story.text) html += '<p>' + escapeHtml(story.text).replace(/\n/g, '<br>') + '</p>';
                html += '</div>';
            }
        }
        if (data.quotes) {
            html += '<h3>语音</h3>';
            for (const [key, quote] of Object.entries(data.quotes)) {
                html += '<div class="quote-section">';
                html += '<h4>' + escapeHtml(quote.title || '语音' + key) + '</h4>';
                if (quote.text) html += '<p>' + escapeHtml(quote.text).replace(/\n/g, '<br>') + '</p>';
                html += '</div>';
            }
        }
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

async function showMaterialDetail(materialId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    const url = MATERIAL_BASE + materialId + '.json?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let html = '<h2>' + escapeHtml(data.name) + '</h2>';
        if (data.rarity) html += '<p><strong>稀有度：</strong>' + data.rarity + '星</p>';
        if (data.type) html += '<p><strong>类型：</strong>' + escapeHtml(data.type) + '</p>';
        if (data.description) html += '<p><strong>描述：</strong><br>' + escapeHtml(data.description).replace(/\n/g, '<br>') + '</p>';
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

async function showWeaponDetail(weaponId, name) {
    const displayDiv = document.getElementById('contentDisplay');
    displayDiv.innerHTML = '<div class="loading">加载中...</div>';
    const url = WEAPON_BASE + weaponId + '.json?v=' + Date.now();
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        let html = '<h2>' + escapeHtml(data.name) + '</h2>';
        if (data.rank) html += '<p><strong>星级：</strong>' + data.rank + '星</p>';
        if (data.type) html += '<p><strong>类型：</strong>' + escapeHtml(data.type) + '</p>';
        if (data.description) html += '<p><strong>描述：</strong><br>' + escapeHtml(data.description).replace(/\n/g, '<br>') + '</p>';
        if (data.story) html += '<p><strong>故事：</strong><br>' + escapeHtml(data.story).replace(/\n/g, '<br>') + '</p>';
        if (data.affix) {
            html += '<h3>武器特效</h3>';
            for (const [key, affix] of Object.entries(data.affix)) {
                html += '<h4>' + escapeHtml(affix.name) + '</h4><ul>';
                for (const [level, desc] of Object.entries(affix.upgrade)) {
                    html += '<li><strong>精炼' + level + '阶：</strong> ' + escapeHtml(desc) + '</li>';
                }
                html += '</ul>';
            }
        }
        displayDiv.innerHTML = html;
    } catch (err) {
        displayDiv.innerHTML = '<div class="error">加载失败：' + err.message + '</div>';
    }
}

initTree();
</script>
</body>
</html>
'''


def main():
    print("Loading tree data...")

    # Load quest trees (nested)
    quest_tree = load_quest_trees()
    print(f"  Quest tree: {len(quest_tree.get('children', []))} sub-categories")

    # Load flat trees
    flat_trees = load_flat_trees()
    print(f"  Flat trees: {len(flat_trees)} categories")

    # Combine all into one root
    root = {
        "name": "root",
        "children": [quest_tree] + flat_trees,
    }

    # Serialize to JSON for embedding
    tree_json = json.dumps(root, ensure_ascii=False)

    # Generate HTML
    html = HTML_TEMPLATE.replace("__TREE_DATA_PLACEHOLDER__", tree_json)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nGenerated: {OUTPUT}")
    print(f"  File size: {os.path.getsize(OUTPUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
