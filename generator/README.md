# 大嵓埜 多言語動画生成システム

毎月のコースメニューを **12言語 × 2コース = 24パターン** の Instagram リール動画に自動変換します。

---

## 対応言語（12言語）

| コード | 言語 |
|--------|------|
| `ja` | 日本語 |
| `en` | English |
| `zh_cn` | 中文（简体） |
| `zh_tw` | 中文（繁體） |
| `ko` | 한국어 |
| `fr` | Français |
| `de` | Deutsch |
| `th` | ไทย |
| `pt` | Português |
| `pt_br` | Português (BR) |
| `tl` | Filipino |
| `vi` | Tiếng Việt |

---

## 毎月の更新手順

### ステップ 1: 写真を準備する

新しい月の料理写真を `processed/` フォルダに入れてください。

- 形式: PNG または JPG
- 推奨サイズ: 1080×1920 以上（縦長）
- 必要枚数: 1コースあたり 10枚（料理）+ 1枚（タイトル/エンディング用）

### ステップ 2: menu.json を更新する

`generator/menu.json` を編集します。

**変更が必要な箇所:**

1. `"month"` — 月を更新（例: `"2025-04"`）
2. 各料理の `"image"` — 写真のパスを更新
3. 各料理の `"category"` と `"description"` — 12言語の料理名・説明を更新

**menu.json の構成:**

```
menu.json
├── month          ← 月（表示用）
├── store          ← 店舗情報（通常は変更不要）
│   ├── name       ← 店名（12言語）
│   ├── subtitle   ← サブタイトル（12言語）
│   ├── address    ← 住所（12言語）
│   ├── phone      ← 電話番号
│   ├── hours      ← 営業時間（12言語）
│   └── reservation← 予約案内（12言語）
└── courses        ← コース定義
    ├── seiran     ← 青藍色コース
    │   ├── name   ← コース名（12言語）
    │   ├── price  ← 価格
    │   ├── title_image  ← タイトル背景画像
    │   ├── ending_image ← エンディング背景画像
    │   └── dishes[]     ← 料理リスト（10品）
    │       ├── image       ← 料理写真パス
    │       ├── category    ← 料理カテゴリ名（12言語）
    │       └── description ← 食材説明（12言語）
    └── kikyou     ← 桔梗色コース（同構成）
```

### ステップ 3: 動画を生成する

```bash
# 全言語・全コース生成（24パターン）
python3 generator/generate.py

# 特定の言語だけ生成
python3 generator/generate.py --lang ja
python3 generator/generate.py --lang en --lang ko

# 特定のコースだけ生成
python3 generator/generate.py --course seiran

# 特定の言語 × コースの組み合わせ
python3 generator/generate.py --lang fr --course kikyou
```

### ステップ 4: 確認する

生成された動画は以下のフォルダに出力されます:

| フォルダ | コース | 言語 |
|---------|--------|------|
| `output/` | 青藍色 | 日本語 |
| `output_en/` | 青藍色 | English |
| `output_ko/` | 青藍色 | 한국어 |
| `output2/` | 桔梗色 | 日本語 |
| `output2_en/` | 桔梗色 | English |
| ... | ... | ... |

各フォルダの内容:
```
output_en/
├── 00_title.mp4              ← タイトル（2.5秒）
├── 01_clip.mp4 〜 10_clip.mp4 ← 料理クリップ（各1.7秒）
├── 11_ending.mp4             ← エンディング（3.5秒）
└── okurano_seiran_en_reel.mp4 ← 統合リール動画
```

---

## その他のコマンド

```bash
# 対応言語の一覧を表示
python3 generator/generate.py --list

# 別のメニューファイルを指定
python3 generator/generate.py --menu path/to/other_menu.json
```

---

## 必要な環境

- Python 3.6 以上
- FFmpeg（`ffmpeg` コマンドが使える状態）
- Noto Serif フォント（CJK, Thai 含む）

---

## トラブルシューティング

**Q: 「画像が見つかりません」と表示される**
→ `menu.json` の `"image"` パスを確認してください。プロジェクトルートからの相対パスです。

**Q: テキストが文字化けする**
→ フォントがインストールされているか確認してください: `fc-list | grep "Noto Serif"`

**Q: 特定の言語だけ生成し直したい**
→ `--lang` オプションで指定: `python3 generator/generate.py --lang ko`
