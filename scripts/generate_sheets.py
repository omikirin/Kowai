#!/usr/bin/env python3
"""『おむかえのお願い』20pシート画像を fal.ai で生成する。

data/omukae_name_sheets.json の各シート(5列x4行=20ページ、右上起点・右→左)を
1枚の画像として生成し、sheets/sheet_omukae_{nn}.png に保存する。
セリフは画像に焼き込まず、リーダー(index.html)側でオーバーレイ描画する。

使い方:
    FAL_KEY=xxxx python3 scripts/generate_sheets.py [--sheet N] [--model MODEL]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = "fal-ai/flux/dev"
# シート比率 3360:2360 ≒ 1.42:1(仕様の practical 解像度)。
# モデル側の上限に収まるサイズで生成し、リーダー側は比率でクロップするため解像度非依存。
WIDTH, HEIGHT = 1420, 1000


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


def expand_chars(prompt, chars):
    """{char_id} を characters.json の anchor_prompt に展開する。"""
    def rep(m):
        c = chars.get(m.group(1))
        return f"({c['anchor_prompt']})" if c else m.group(0)
    return re.sub(r"\{(\w+)\}", rep, prompt)


def build_prompt(sheet, fmt, chars, style_suffix):
    lines = [
        "manga page sheet, strict uniform 5 columns x 4 rows grid of 20 vertical manga pages,"
        " no gutter, no border, read right to left, page 1 at top-right,",
    ]
    n_pages = 0
    for pg in sheet["pages"]:
        if not isinstance(pg["page"], int):  # "49-60" 等の空白セル指定
            continue
        panels = "; ".join(p["prompt"] for p in pg["panels"])
        panels = expand_chars(panels, chars)
        lines.append(f"page {pg['page']}: {panels}")
        n_pages += 1
    if n_pages < 20:
        lines.append(f"remaining {20 - n_pages} grid cells: solid black fill")
    lines.append("no text, no speech bubbles, no lettering,")
    lines.append(style_suffix)
    return "\n".join(lines)


def fal_generate(model, prompt, key):
    """fal.ai queue API で生成し、画像URLを返す。"""
    base = f"https://queue.fal.run/{model}"
    body = json.dumps({
        "prompt": prompt[:5000],
        "image_size": {"width": WIDTH, "height": HEIGHT},
        "num_inference_steps": 40,
        "enable_safety_checker": True,
    }).encode()
    req = urllib.request.Request(base, data=body, headers={
        "Authorization": f"Key {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        sub = json.load(r)
    status_url = sub["status_url"]
    response_url = sub["response_url"]
    for _ in range(120):
        time.sleep(3)
        req = urllib.request.Request(status_url, headers={"Authorization": f"Key {key}"})
        with urllib.request.urlopen(req) as r:
            st = json.load(r)
        if st["status"] == "COMPLETED":
            break
        if st["status"] in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal job failed: {st}")
    else:
        raise TimeoutError("fal job did not complete in time")
    req = urllib.request.Request(response_url, headers={"Authorization": f"Key {key}"})
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    return out["images"][0]["url"]


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
        out_path = os.path.join(ROOT, "sheets", f"sheet_omukae_{n:02d}.png")
        prompt = build_prompt(sheet, name_sheets["format"], chars, style)
        print(f"[sheet {n}] generating ({sheet['pages_range']}) ...", flush=True)
        url = fal_generate(args.model, prompt, key)
        urllib.request.urlretrieve(url, out_path)
        print(f"[sheet {n}] saved -> {out_path}")


if __name__ == "__main__":
    main()
