#!/usr/bin/env python3
"""『おむかえのお願い』20pシート画像を fal.ai で生成する。

1シート丸ごとの生成では拡散モデルが 5x4 グリッドを守れないため、
ページ単位で生成し、Pillow で 5列x4行(右上=P1、右→左)に合成する。
足りないセルは黒ベタ。モノクロ原作のためグレースケール化して保存する。
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
DEFAULT_MODEL = "fal-ai/flux/dev"
COLS, ROWS = 5, 4
PW, PH = 672, 1184  # 1ページの生成サイズ(仕様の 672:1180 比にほぼ一致、8の倍数)


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


def expand_chars(prompt, chars):
    """{char_id} を characters.json の anchor_prompt に展開する。"""
    def rep(m):
        c = chars.get(m.group(1))
        return f"({c['anchor_prompt']})" if c else m.group(0)
    return re.sub(r"\{(\w+)\}", rep, prompt)


def build_page_prompt(page, chars, style_suffix):
    n = len(page["panels"])
    lines = [
        f"single vertical manga page, {n} stacked panel{'s' if n > 1 else ''} from top to bottom,"
        if n > 1 else "single full-page manga panel,",
    ]
    for i, p in enumerate(page["panels"], 1):
        lines.append(f"panel {i}: {expand_chars(p['prompt'], chars)}")
    lines.append("no text, no speech bubbles, no lettering,")
    lines.append("monochrome black and white ink only,")
    lines.append(style_suffix)
    return "\n".join(lines)


def fal_generate(model, prompt, key):
    """fal.ai queue API で1ページ生成し、画像バイト列を返す。"""
    base = f"https://queue.fal.run/{model}"
    body = json.dumps({
        "prompt": prompt[:5000],
        "image_size": {"width": PW, "height": PH},
        "num_inference_steps": 28,
        "enable_safety_checker": True,
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
        pages_dir = os.path.join(ROOT, "sheets", "pages")
        os.makedirs(pages_dir, exist_ok=True)
        canvas = Image.new("L", (PW * COLS, PH * ROWS), 0)  # 空セルは黒ベタ
        for pg in sheet["pages"]:
            if not isinstance(pg["page"], int):  # "49-60" 等の空白セル指定
                continue
            cache = os.path.join(pages_dir, f"p{pg['page']:02d}.png")
            if os.path.exists(cache):  # 再実行時は生成済みページを再利用
                img = Image.open(cache).convert("L")
            else:
                prompt = build_page_prompt(pg, chars, style)
                print(f"[sheet {n}] P{pg['page']} ({pg['scene']}) ...", flush=True)
                for attempt in range(3):
                    try:
                        raw = fal_generate(args.model, prompt, key)
                        break
                    except Exception as e:
                        print(f"[sheet {n}] P{pg['page']} attempt {attempt+1} failed: {e}", flush=True)
                        if attempt == 2:
                            raise
                        time.sleep(10)
                img = Image.open(io.BytesIO(raw)).convert("L").resize((PW, PH))
                img.save(cache)
            k = (pg["page"] - 1) % (COLS * ROWS)
            row, col = k // COLS, COLS - 1 - (k % COLS)
            canvas.paste(img, (col * PW, row * PH))
        out_path = os.path.join(ROOT, "sheets", f"sheet_omukae_{n:02d}.png")
        canvas.save(out_path)
        print(f"[sheet {n}] saved -> {out_path}")


if __name__ == "__main__":
    main()
