#!/usr/bin/env python3
"""『おむかえのお願い』16pシート画像を fal.ai (Nano Banana Pro) で生成する。

data/omukae_name_sheets.json の全ページを16p単位に分割し、各シート
(4列x4行=16ページ、右上起点・右→左)を1枚の画像として生成して
sheets/sheet_omukae_{nn}.png に保存する。
モノクロ原作のためグレースケール化して保存。
セリフは画像に焼き込まず、リーダー(index.html)側でオーバーレイ描画する。

使い方:
    FAL_KEY=xxxx python3 scripts/generate_sheets.py [--sheet N] [--model MODEL]
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = "fal-ai/nano-banana-pro"
COLS, ROWS = 4, 4  # 1シート=16ページ
# シートは縦長(4列x4行、各ページ672:1180)→ 全体比 2688:4720 ≒ 0.569。
# Nano Banana Pro のプリセット比では 9:16(0.5625) が最も近い。
ASPECT_RATIO = "9:16"
RESOLUTION = "4K"


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


def expand_chars(prompt, chars):
    """{char_id} を characters.json の anchor_prompt に展開する。"""
    def rep(m):
        c = chars.get(m.group(1))
        return f"({c['anchor_prompt']})" if c else m.group(0)
    return re.sub(r"\{(\w+)\}", rep, prompt)


def build_sheet_prompt(pages, chars, style_suffix):
    pps = COLS * ROWS
    lines = [
        f"A single contact-sheet image containing exactly {pps} manga pages arranged in a strict"
        f" uniform grid of {COLS} columns x {ROWS} rows (equal-sized cells, no gutter, no outer margin).",
        f"Reading order is right-to-left, row by row: the first page is the TOP-RIGHT cell, the"
        f" first {COLS} pages fill the top row from right to left, the next page starts the second"
        f" row at the right, and the last cell is at the BOTTOM-LEFT.",
        "Each cell is one vertical manga page whose panels are stacked top to bottom.",
        "Page contents (in reading order):",
    ]
    for pg in pages:
        panels = " / ".join(
            f"panel {p['no']}: {expand_chars(p['prompt'], chars)}" for p in pg["panels"])
        lines.append(f"- page {pg['page']}: {panels}")
    if len(pages) < pps:
        lines.append(
            f"- the remaining {pps - len(pages)} cells are SOLID BLACK fill, completely empty.")
    lines.append(
        "No text, no speech bubbles, no lettering, no page numbers anywhere in the image.")
    lines.append("Entirely monochrome black-and-white ink artwork.")
    lines.append(f"Art style: {style_suffix}")
    return "\n".join(lines)


def fal_generate(model, prompt, key):
    """fal.ai queue API で生成し、画像バイト列を返す。"""
    base = f"https://queue.fal.run/{model}"
    body = json.dumps({
        "prompt": prompt[:30000],
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "num_images": 1,
        "output_format": "png",
    }).encode()
    req = urllib.request.Request(base, data=body, headers={
        "Authorization": f"Key {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        sub = json.load(r)
    for _ in range(200):
        time.sleep(3)
        req = urllib.request.Request(sub["status_url"], headers={"Authorization": f"Key {key}"})
        with urllib.request.urlopen(req) as r:
            st = json.load(r)
        if st["status"] == "COMPLETED":
            break
        if st["status"] in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal job failed: {st}")
    else:
        raise TimeoutError("fal job did not complete in time")
    req = urllib.request.Request(sub["response_url"], headers={"Authorization": f"Key {key}"})
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    with urllib.request.urlopen(out["images"][0]["url"]) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", type=int, help="このシート番号のみ生成 (1-3)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--data", default="omukae_name_sheets.json", help="data/内のネームJSON")
    ap.add_argument("--chars", default="omukae_characters.json", help="data/内のキャラ設定JSON")
    ap.add_argument("--prefix", default="sheet_omukae", help="出力ファイル名の接頭辞")
    args = ap.parse_args()

    key = os.environ.get("FAL_KEY")
    if not key:
        sys.exit("FAL_KEY 環境変数を設定してください (https://fal.ai/dashboard/keys)")

    name_sheets = load(args.data)
    characters = load(args.chars)
    chars = characters["characters"]
    style = characters["style_suffix"]

    # ネームJSONは20p単位のグループだが、シートは16p単位で再分割する
    all_pages = [pg for sh in name_sheets["sheets"] for pg in sh["pages"]
                 if isinstance(pg["page"], int)]
    all_pages.sort(key=lambda p: p["page"])
    pps = COLS * ROWS
    chunks = [all_pages[i:i + pps] for i in range(0, len(all_pages), pps)]

    os.makedirs(os.path.join(ROOT, "sheets"), exist_ok=True)
    for n, pages in enumerate(chunks, 1):
        if args.sheet and n != args.sheet:
            continue
        prompt = build_sheet_prompt(pages, chars, style)
        print(f"[sheet {n}] generating (P{pages[0]['page']}-P{pages[-1]['page']}) ...", flush=True)
        for attempt in range(3):
            try:
                raw = fal_generate(args.model, prompt, key)
                break
            except Exception as e:
                print(f"[sheet {n}] attempt {attempt + 1} failed: {e}", flush=True)
                if attempt == 2:
                    raise
                time.sleep(10)
        img = Image.open(io.BytesIO(raw)).convert("L")
        out_path = os.path.join(ROOT, "sheets", f"{args.prefix}_{n:02d}.png")
        img.save(out_path)
        # リーダーが優先的に読む軽量版(約1/5サイズ)
        img.save(out_path[:-4] + ".webp", "WEBP", quality=82, method=6)
        print(f"[sheet {n}] saved -> {out_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
