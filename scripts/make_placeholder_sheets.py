#!/usr/bin/env python3
"""Fal生成前の動作確認用に、ネームJSONからプレースホルダーシートを作る。

5x4グリッド(右上=P1、右→左)にページ番号・シーン名・パネル枠を描いた
モノクロのダミー画像を sheets/sheet_omukae_{nn}.png に出力する。
本番は scripts/generate_sheets.py (要 FAL_KEY) で上書きする。
"""
import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS, ROWS = 4, 4
PW, PH = 672, 590  # 仕様 practical: 1ページ 672x590


def main():
    with open(os.path.join(ROOT, "data", "omukae_name_sheets.json"), encoding="utf-8") as f:
        name_sheets = json.load(f)
    os.makedirs(os.path.join(ROOT, "sheets"), exist_ok=True)

    # ネームJSONは20p単位のグループだが、シートは16p単位で再分割する
    pps = COLS * ROWS
    all_pages = [pg for sh in name_sheets["sheets"] for pg in sh["pages"]
                 if isinstance(pg["page"], int)]
    all_pages.sort(key=lambda p: p["page"])
    chunks = [all_pages[i:i + pps] for i in range(0, len(all_pages), pps)]

    for sheet_no, pages in enumerate(chunks, 1):
        img = Image.new("L", (PW * COLS, PH * ROWS), 8)
        d = ImageDraw.Draw(img)
        for pg in pages:
            k = (pg["page"] - 1) % pps
            row, col = k // COLS, COLS - 1 - (k % COLS)
            x, y = col * PW, row * PH
            d.rectangle([x + 2, y + 2, x + PW - 3, y + PH - 3], fill=235, outline=40, width=2)
            n_panels = len(pg["panels"])
            pad, top = 14, 40
            panel_h = (PH - top - pad - (n_panels - 1) * 8) // n_panels
            for i in range(n_panels):
                py = y + top + i * (panel_h + 8)
                d.rectangle([x + pad, py, x + PW - pad, py + panel_h], outline=60, width=3)
                d.line([x + pad, py, x + PW - pad, py + panel_h], fill=180, width=1)
                d.line([x + pad, py + panel_h, x + PW - pad, py], fill=180, width=1)
            d.text((x + pad, y + 10), f"P{pg['page']}  {pg['scene']}", fill=30)
        out = os.path.join(ROOT, "sheets", f"sheet_omukae_{sheet_no:02d}.png")
        img.save(out)
        print("saved", out)


if __name__ == "__main__":
    main()
