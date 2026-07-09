# おむかえのお願い — 16pシートリーダー

1枚の画像に16ページ(4列×4行・右上起点・右→左)を敷き詰めた「シート」を、
ブラウザ上で見開き/単ページ/一覧表示する電子リーダー。

## 構成

- `index.html` — リーダー本体。`sheets/sheet_omukae_01.png…` を自動読込(手動でのファイル選択も可)。
  セリフ・SFXは `data/omukae_name_sheets.json` からページ上にオーバーレイ描画する(「セリフ」ボタンで切替)。
- `data/` — キャラ設定・シート版ネーム・リーダー仕様のJSON。
- `scripts/generate_sheets.py` — fal.ai でシート3枚を生成(`FAL_KEY` 必須)。
- `scripts/make_placeholder_sheets.py` — 動作確認用プレースホルダーシートの生成(要 Pillow)。
- `sheets/` — シート画像。現在はプレースホルダー。Fal生成で上書きする。

## 使い方

```sh
python3 -m http.server 8000   # リポジトリ直下で
# → http://localhost:8000/index.html
```

操作: 左タップ / ←キー / 右スワイプで次へ(右開き)。20p一覧のセルをタップでそのページへジャンプ。

## Falでのシート生成

```sh
FAL_KEY=xxxx python3 scripts/generate_sheets.py            # 3枚すべて
FAL_KEY=xxxx python3 scripts/generate_sheets.py --sheet 2  # 1枚のみ
FAL_KEY=xxxx python3 scripts/generate_sheets.py --model fal-ai/nano-banana-pro
```

ページ番号 n のクロップ規則: `col = 3 - ((n-1) % 4)`, `row = floor((n-1) / 4)`(仕様は `data/sheet_reader_spec.json`)。
