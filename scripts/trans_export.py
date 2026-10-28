#!/usr/bin/env python3
"""trans_export.py — 全量文本按类别分块导出为 AI 翻译 txt。

格式（每条目 4 行 + 空行）:
  # 00042 [上下文] @容器路径
  > 日文原文（转义）
  < 中文译文（空 = 未翻译）
分块: 每个输出 txt ≤ 300 条目, 文件名 <类别>_<序号>.txt
输出: <目录>/<类别>_<NN>.txt + manifest.json（校验用）
"""
import json
import os
import re
import sys

CHUNK = 300

CATEGORIES = [
    ("系统与菜单", re.compile(r"GA_TEXT_J\.NBL/(WindowText|ObjectText|MemoryCard|PlayerText|DungeonLobbyText|QuestText)_")),
    ("道具与装备", re.compile(r"GA_TEXT_J\.NBL/Item")),
    ("敌人与战斗", re.compile(r"GA_TEXT_J\.NBL/(EnemyText|BossText)_")),
    ("角色台词", re.compile(r"GA_APC_WORDS_J\.NBL/")),
    ("任务文本", re.compile(r"FA_QE_TABLE")),
    ("剧情文本", re.compile(r"XF_QE_.*STORY")),
    ("剧情事件", re.compile(r"XF_QE_")),
]

KANA = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")


def is_japanese(path: str, strs) -> bool:
    """过滤多语言残留: GA 只留 _J; QE/其他容器需含假名。"""
    top = path.split("/")[0]
    if top.startswith("GA_"):
        return top in ("GA_TEXT_J.NBL", "GA_APC_WORDS_J.NBL")
    # QE 多语言任务: 按内容判日文
    return any(KANA.search(s) for s in strs)


def build_refs(data):
    """为每个日文容器找官方繁中参考容器（同 AFS、同子路径、同串数）。
    返回 {日文路径: [繁中串...]}"""
    import re as _re
    cjk = _re.compile(r"[\u4E00-\u9FFF]")
    groups = {}
    for p, strs in data.items():
        if "#" not in p.split("/")[0]:
            continue
        if not any(s.strip() for s in strs):
            continue
        top = p.split("/")[0]
        idx = top.split("#")[1]
        rest = p.split("/", 1)[1] if "/" in p else ""
        base = top.split("#")[0]
        ss = [s for s in strs if s.strip()]
        if any(KANA.search(s) for s in ss):
            groups.setdefault((base, rest), {})["JP:" + idx] = strs
        elif ss and any(cjk.search(s) for s in ss) and not any(
                s.strip().isascii() for s in ss[:3]):
            groups.setdefault((base, rest), {})["ZH:" + idx] = strs
    refs = {}
    for (base, rest), langs in groups.items():
        jp_items = [(k, v) for k, v in langs.items() if k.startswith("JP:")]
        zh_items = [(k, v) for k, v in langs.items() if k.startswith("ZH:")]
        for jk, jstrs in jp_items:
            jidx = jk.split(":")[1]
            cand = [z for zk, z in zh_items if len(z) == len(jstrs)]
            if len(cand) >= 1:
                refs[f"{base}#{jidx}/{rest}"] = cand[0]
    return refs


def categorize(path: str) -> str:
    for name, pat in CATEGORIES:
        if pat.search(path):
            return name
    return "其他文本"


def esc(s: str) -> str:
    return (s.replace("\\", "\\\\")
             .replace("\n", "\\n")
             .replace("\r", "\\r")
             .replace("\t", "\\t"))


def context_tag(path, s):
    if "WindowText" in path:
        return "窗口/菜单"
    if "ObjectText" in path:
        return "对象/按钮"
    if "MemoryCard" in path:
        return "系统消息"
    if "PlayerText" in path:
        return "角色创建"
    if "DungeonLobby" in path:
        return "大厅/设施"
    if "QuestText" in path:
        return "任务菜单"
    if "Item" in path:
        return "道具/装备"
    if "Enemy" in path or "Boss" in path:
        return "敌人"
    if "APC_WORDS" in path:
        return "台词"
    if "text_result" in path:
        return "任务结算"
    if "unit_title" in path:
        return "小节标题"
    if "text.bin" in path:
        return "任务说明"
    if len(s) > 30:
        return "长文本"
    return "文本"


PRESET = {"はい": "是", "いいえ": "否", "戻る": "返回", "決定": "确认",
          "キャンセル": "取消", "終了": "结束", "設定完了": "设定完成",
          "種族": "种族", "性別": "性别", "次の設定へ": "下一项"}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "work/all_text.json"
    out_root = sys.argv[2] if len(sys.argv) > 2 else "work/translation"
    data = json.load(open(src, encoding="utf-8"))["texts"]
    os.makedirs(out_root, exist_ok=True)

    # 分类别收集 (容器保持排序; 先过滤语言; 附官方繁中参考)
    by_cat = {}
    n_filtered = 0
    refs = build_refs(data)
    print(f"(官方繁中参考配对: {len(refs)} 个日文容器)")
    for path, strs in sorted(data.items()):
        if not any(s.strip() for s in strs):
            continue
        if not is_japanese(path, strs):
            n_filtered += 1
            continue
        by_cat.setdefault(categorize(path), []).append((path, strs))
    print(f"(语言过滤剔除 {n_filtered} 个非日文容器)")

    seq = 0
    manifest = {}
    for cat, items in sorted(by_cat.items()):
        entries = []  # (seq, ctx, path, idx, jp)
        for path, strs in items:
            for i, s in enumerate(strs):
                entries.append((seq, context_tag(path, s), path, i, s))
                seq += 1
        # 分块
        n_files = (len(entries) + CHUNK - 1) // CHUNK
        for fi in range(n_files):
            chunk = entries[fi * CHUNK:(fi + 1) * CHUNK]
            name = f"{cat}_{fi + 1:02d}.txt"
            containers = sorted({e[2] for e in chunk})
            manifest[name] = containers
            with open(os.path.join(out_root, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(f"【类别】{cat}  本文件 {len(chunk)} 条\n")
                f.write("【规则】只改 < 行；格式符/转义/字库限制见 docs/翻译格式说明.md\n\n")
                for s_, ctx, path, idx, jp in chunk:
                    f.write(f"# {s_:05d} [{ctx}] @{path}:{idx}\n")
                    f.write(f"> {esc(jp)}\n")
                    ref = refs.get(path)
                    if ref and idx < len(ref) and ref[idx].strip():
                        f.write(f"= {esc(ref[idx])}\n")
                    f.write(f"< {PRESET.get(jp, '')}\n\n")

    # 全局词条库: 唯一句按出现频次排序（先翻这个收益最大）
    # 字符级参考: 从容器配对中收集 日文串 -> 繁中串
    str_ref = {}
    for path, ref in refs.items():
        jp_strs = data[path]
        for a, b in zip(jp_strs, ref):
            if a.strip() and b.strip() and a not in str_ref:
                str_ref[a] = b
    freq = {}
    for cat, items in by_cat.items():
        for path, strs in items:
            for s in strs:
                if s.strip():
                    freq[s] = freq.get(s, 0) + 1
    uniques = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    gloss_chunks = (len(uniques) + CHUNK - 1) // CHUNK
    for gi in range(gloss_chunks):
        chunk = uniques[gi * CHUNK:(gi + 1) * CHUNK]
        name = f"词条库_{gi + 1:02d}.txt" if gloss_chunks > 1 else "词条库.txt"
        manifest[name] = ["GLOSSARY"]
        with open(os.path.join(out_root, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"【类别】全局词条库(唯一句 ×{len(chunk)}，按出现次数排序)  本文件 {len(chunk)} 条\n")
            f.write("【说明】此处译文会自动应用到所有出现该句的地方；分文件中的同句译文优先级更高\n\n")
            base = gi * CHUNK
            for k, (jp, cnt) in enumerate(chunk):
                f.write(f"# {base + k:05d} [×{cnt}次] @GLOSSARY:{base + k}\n")
                f.write(f"> {esc(jp)}\n")
                if jp in str_ref:
                    f.write(f"= {esc(str_ref[jp])}\n")
                f.write(f"< {PRESET.get(jp, '')}\n\n")

    with open(os.path.join(out_root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("导出完成:")
    for cat, items in sorted(by_cat.items()):
        n = sum(len(s) for _, s in items)
        nf = (sum(len(x[1]) for x in items) + CHUNK - 1) // CHUNK
        print(f"  {cat}: {n} 串 / {nf} 文件")
    print(f"  词条库: {len(uniques)} 唯一句 / {gloss_chunks} 文件")
    print(f"总计 {seq} 条 -> {out_root}")


if __name__ == "__main__":
    main()
