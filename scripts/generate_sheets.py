#!/usr/bin/env python3
"""『おむかえのお願い』20pシート画像を fal.ai (Nano Banana Pro) で生成する。

data/omukae_name_sheets.json の各シート(5列x4行=20ページ、右上起点・右→左)を
1枚の画像として生成し、sheets/sheet_omukae_{nn}.png に保存する。
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
# シートは縦長(5列x4行、各ページ672:1180)→ 全体比 3360:4720 ≒ 0.712。
# Nano Banana Pro のプリセット比では 3:4(0.75) / 2:3(0.667) が近い。
ASPECT_RATIO = "3:4"
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


def build_sheet_prompt(sheet, chars, style_suffix):
    lines = [
        "A single contact-sheet image containing exactly 20 manga pages arranged in a strict"
        " uniform grid of 5 columns x 4 rows (equal-sized cells, no gutter, no outer margin).",
        "Reading order is right-to-left, row by row: page 1 is the TOP-RIGHT cell, pages 1-5"
        " fill the top row from right to left, page 6 starts the second row at the right, and"
        " page 20 is the BOTTOM-LEFT cell.",
        "Each cell is one vertical manga page whose panels are stacked top to bottom.",
        "Page contents:",
    ]
    n_pages = 0
    for pg in sheet["pages"]:
        if not isinstance(pg["page"], int):  # "49-60" 等の空白セル指定
            continue
        panels = " / ".join(
            f"panel {p['no']}: {expand_chars(p['prompt'], chars)}" for p in pg["panels"])
        lines.append(f"- page {pg['page']}: {panels}")
        n_pages += 1
    if n_pages < 20:
        lines.append(
            f"- the remaining {20 - n_pages} cells (after page {sheet['pages'][n_pages - 1]['page']}"
            " in reading order) are SOLID BLACK fill, completely empty.")
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
    args = ap.parse_args()

    key = os.environ.get("FAL_KEY")
    if not key:
        sys.exit("FAL_KEY 環境変数を設定してください (https://fal.ai/dashboard/keys)")

    name_sheets = load("omukae_name_sheets.json")
    characters = load("omukae_characters.json")
    chars = characters["characters"]
    style = characters["style_suffix"]

    os.makedirs(os.path.join(ROOT, "sheets"), exist_ok=True)
    for sheet in name_sheets["sheets"]:
        n = sheet["sheet"]
        if args.sheet and n != args.sheet:
            continue
        prompt = build_sheet_prompt(sheet, chars, style)
        print(f"[sheet {n}] generating ({sheet['pages_range']}) ...", flush=True)
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
        out_path = os.path.join(ROOT, "sheets", f"sheet_omukae_{n:02d}.png")
        img.save(out_path)
        print(f"[sheet {n}] saved -> {out_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
