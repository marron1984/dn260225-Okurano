#!/usr/bin/env python3
"""
大嵓埜 多言語動画自動生成スクリプト

使い方:
  python generator/generate.py                           全言語・全コース生成
  python generator/generate.py --lang ja                 日本語のみ
  python generator/generate.py --lang en --lang ko       英語と韓国語
  python generator/generate.py --course seiran           青藍色コースのみ
  python generator/generate.py --lang fr --course kikyou フランス語・桔梗色のみ
  python generator/generate.py --list                    対応言語一覧を表示
"""

import json
import subprocess
import os
import sys
import argparse
import shutil
from pathlib import Path

# ============================================================
# 設定
# ============================================================

# 動画の解像度とタイミング
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# コースごとのタイミング設定（1.25倍適用済み）
COURSE_TIMING = {
    "seiran": {
        "title": 3.125,    # 2.5 × 1.25
        "clip": 2.125,     # 1.7 × 1.25
        "ending": 4.375,   # 3.5 × 1.25
        "title_brightness": -0.08,
        "ending_brightness": -0.15,
    },
    "kikyou": {
        "title": 4.375,    # 3.5 × 1.25
        "clip": 3.125,     # 2.5 × 1.25
        "ending": 5.0,     # 4.0 × 1.25
        "title_brightness": -0.45,   # さらに暗く → 白文字を際立たせる
        "ending_brightness": -0.50,  # さらに暗く → 文字を際立たせる
    },
}

# デフォルト（フォールバック用）
TITLE_DURATION = 3.125
CLIP_DURATION = 2.125
ENDING_DURATION = 4.375

# テキストスタイル（色はFFmpeg形式）
COLOR_GOLD = "E8D0A0"
COLOR_WHITE = "FFFFFF"
COLOR_GRAY = "AAAAAA"

# 言語ごとのフォント設定
FONTS = {
    "ja":    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "en":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "zh_cn": "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "zh_tw": "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "ko":    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "fr":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "de":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "th":    "/usr/share/fonts/truetype/noto/NotoSerifThai-Regular.ttf",
    "pt":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "pt_br": "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "tl":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "vi":    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
}

# 言語表示名（ログ用）
LANG_NAMES = {
    "ja":    "日本語",
    "en":    "English",
    "zh_cn": "中文（简体）",
    "zh_tw": "中文（繁體）",
    "ko":    "한국어",
    "fr":    "Français",
    "de":    "Deutsch",
    "th":    "ไทย",
    "pt":    "Português",
    "pt_br": "Português (BR)",
    "tl":    "Filipino",
    "vi":    "Tiếng Việt",
}

# 出力ディレクトリのマッピング
OUTPUT_DIRS = {
    ("seiran", "ja"):    "output",
    ("seiran", "en"):    "output_en",
    ("seiran", "zh_cn"): "output_zh_cn",
    ("seiran", "zh_tw"): "output_zh_tw",
    ("seiran", "ko"):    "output_ko",
    ("seiran", "fr"):    "output_fr",
    ("seiran", "de"):    "output_de",
    ("seiran", "th"):    "output_th",
    ("seiran", "pt"):    "output_pt",
    ("seiran", "pt_br"): "output_pt_br",
    ("seiran", "tl"):    "output_tl",
    ("seiran", "vi"):    "output_vi",
    ("kikyou", "ja"):    "output2",
    ("kikyou", "en"):    "output2_en",
    ("kikyou", "zh_cn"): "output2_zh_cn",
    ("kikyou", "zh_tw"): "output2_zh_tw",
    ("kikyou", "ko"):    "output2_ko",
    ("kikyou", "fr"):    "output2_fr",
    ("kikyou", "de"):    "output2_de",
    ("kikyou", "th"):    "output2_th",
    ("kikyou", "pt"):    "output2_pt",
    ("kikyou", "pt_br"): "output2_pt_br",
    ("kikyou", "tl"):    "output2_tl",
    ("kikyou", "vi"):    "output2_vi",
}

ALL_LANGUAGES = list(LANG_NAMES.keys())
ALL_COURSES = ["seiran", "kikyou"]
COURSE_NAMES = {"seiran": "青藍色", "kikyou": "桔梗色"}


# ============================================================
# ヘルパー関数
# ============================================================

def escape_ffmpeg_text(text):
    """FFmpeg drawtext用にテキストをエスケープする"""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def escape_ffmpeg_expr(expr):
    """FFmpegフィルタ式内のカンマをエスケープする"""
    return expr.replace(",", "\\,")


def get_font(lang):
    """言語に応じたフォントパスを返す"""
    return FONTS.get(lang, FONTS["en"])


def run_ffmpeg(args, desc=""):
    """FFmpegコマンドを実行する"""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {desc}")
        print(f"  stderr: {result.stderr[:500]}")
        return False
    return True


def make_slide_up_alpha(delay=0.3, fade_dur=0.5):
    """テキストのスライドアップ+フェードインアニメーション式を生成する"""
    end = round(delay + fade_dur, 2)
    alpha = f"if(lt(t\\,{delay})\\,0\\,if(lt(t\\,{end})\\,min(1\\,(t-{delay})/{fade_dur})\\,1))"
    slide = f"if(lt(t\\,{delay})\\,25\\,if(lt(t\\,{end})\\,25*(1-(t-{delay})/{fade_dur})\\,0))"
    return alpha, slide


# ============================================================
# 動画生成関数
# ============================================================

def generate_title(image_path, store_name, course_name, price, lang, output_path, duration=None, brightness=-0.08):
    """タイトルカード動画を生成する（店名 + コース名 + 価格）"""
    duration = duration or TITLE_DURATION
    font = get_font(lang)
    esc_store = escape_ffmpeg_text(store_name)
    esc_course = escape_ffmpeg_text(course_name)
    esc_price = escape_ffmpeg_text(f"¥{price:,}")

    alpha1, slide1 = make_slide_up_alpha(0.2, 0.6)
    alpha2, slide2 = make_slide_up_alpha(0.3, 0.5)   # コース名を早く表示
    alpha3, slide3 = make_slide_up_alpha(0.5, 0.5)

    # 店名のフォントサイズ（日本語は漢字なので大きめ）
    store_size = 68 if lang == "ja" else 52
    if lang in ("zh_cn", "zh_tw"):
        store_size = 68

    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"eq=brightness={brightness},"
        # 店名
        f"drawtext=text='{esc_store}':"
        f"fontfile='{font}':fontsize={store_size}:fontcolor=#{COLOR_GOLD}:"
        f"x=(w-text_w)/2:y=(h/2-{store_size})+({slide1}):"
        f"alpha={alpha1},"
        # コース名（白文字で目立たせる）
        f"drawtext=text='{esc_course}':"
        f"fontfile='{font}':fontsize=32:fontcolor=#{COLOR_WHITE}:"
        f"x=(w-text_w)/2:y=(h/2+40)+({slide2}):"
        f"alpha={alpha2},"
        # 価格
        f"drawtext=text='{esc_price}':"
        f"fontfile='{font}':fontsize=30:fontcolor=#{COLOR_WHITE}:"
        f"x=(w-text_w)/2:y=(h/2+84)+({slide3}):"
        f"alpha={alpha3}"
    )

    args = [
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        output_path
    ]
    return run_ffmpeg(args, f"タイトル: {output_path}")


def generate_clip(image_path, category, description, lang, output_path, is_summary=False, duration=None):
    """料理クリップ動画を生成する（料理名 + 説明テキスト）"""
    duration = duration or CLIP_DURATION
    font = get_font(lang)

    # カテゴリ名のエスケープとスタイル
    esc_cat = escape_ffmpeg_text(category)

    # カテゴリのフォントサイズ（日本語は140%拡大に合わせて大きく）
    if is_summary:
        cat_size = 40
    elif lang == "ja":
        cat_size = 68       # 52 → 68
    elif lang in ("zh_cn", "zh_tw"):
        cat_size = 62       # 48 → 62
    elif lang == "th":
        cat_size = 52       # 40 → 52
    else:
        cat_size = 56       # 44 → 56

    alpha1, slide1 = make_slide_up_alpha(0.2, 0.5)

    # カテゴリのdrawtext（説明テキスト拡大に合わせてY位置をさらに上に）
    cat_y_base = f"h-400" if not is_summary else f"h-140"
    drawtext_cat = (
        f"drawtext=text='{esc_cat}':"
        f"fontfile='{font}':fontsize={cat_size}:fontcolor=#{COLOR_GOLD}:"
        f"x=(w-text_w)/2:y=({cat_y_base})+({slide1}):"
        f"alpha={alpha1}"
    )

    # 説明テキスト（複数行対応・さらに140%拡大）
    drawtext_descs = ""
    if description.strip():
        lines = description.strip().split("\n")
        desc_size = 43 if lang in ("ja", "zh_cn", "zh_tw") else 39  # 31→43 (×1.4), 28→39
        if lang == "th":
            desc_size = 38  # 27→38
        line_spacing = 59   # 42→59（文字拡大に合わせて行間も広く）
        for i, line in enumerate(lines):
            esc_line = escape_ffmpeg_text(line.strip())
            if not esc_line:
                continue
            line_delay = 0.4 + i * 0.15
            alpha_d, slide_d = make_slide_up_alpha(line_delay, 0.4)
            y_offset = f"h-{290 - i * line_spacing}"
            drawtext_descs += (
                f",drawtext=text='{esc_line}':"
                f"fontfile='{font}':fontsize={desc_size}:fontcolor=#{COLOR_GRAY}:"
                f"x=(w-text_w)/2:y=({y_offset})+({slide_d}):"
                f"alpha={alpha_d}"
            )

    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"{drawtext_cat}"
        f"{drawtext_descs}"
    )

    args = [
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        output_path
    ]
    return run_ffmpeg(args, f"クリップ: {output_path}")


def generate_ending(image_path, store_data, lang, output_path, duration=None, brightness=-0.15):
    """エンディング動画を生成する（店舗情報一覧）"""
    duration = duration or ENDING_DURATION
    font = get_font(lang)

    store_name = escape_ffmpeg_text(store_data["name"].get(lang, store_data["name"]["en"]))
    subtitle = escape_ffmpeg_text(store_data["subtitle"].get(lang, store_data["subtitle"]["en"]))
    address_lines = store_data["address"].get(lang, store_data["address"]["en"]).split("\n")
    phone = escape_ffmpeg_text(store_data["phone"])
    hours_lines = store_data["hours"].get(lang, store_data["hours"]["en"]).split("\n")
    reservation_lines = store_data["reservation"].get(lang, store_data["reservation"]["en"]).split("\n")

    store_size = 74 if lang in ("ja", "zh_cn", "zh_tw") else 58   # 60→74

    # テキスト要素を順番に配置
    elements = []
    y_pos = 150

    # 店名
    alpha, slide = make_slide_up_alpha(0.2, 0.5)
    elements.append(
        f"drawtext=text='{store_name}':"
        f"fontfile='{font}':fontsize={store_size}:fontcolor=#{COLOR_GOLD}:"
        f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
    )
    y_pos += store_size + 24

    # サブタイトル
    alpha, slide = make_slide_up_alpha(0.3, 0.5)
    elements.append(
        f"drawtext=text='{subtitle}':"
        f"fontfile='{font}':fontsize=28:fontcolor=#{COLOR_GRAY}:"  # 22→28
        f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
    )
    y_pos += 65

    # 住所
    for i, line in enumerate(address_lines):
        esc = escape_ffmpeg_text(line.strip())
        if not esc:
            continue
        alpha, slide = make_slide_up_alpha(0.5 + i * 0.1, 0.4)
        elements.append(
            f"drawtext=text='{esc}':"
            f"fontfile='{font}':fontsize=26:fontcolor=#{COLOR_GRAY}:"  # 20→26
            f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
        )
        y_pos += 34
    y_pos += 22

    # 電話番号
    alpha, slide = make_slide_up_alpha(0.8, 0.4)
    elements.append(
        f"drawtext=text='{phone}':"
        f"fontfile='{font}':fontsize=48:fontcolor=#{COLOR_WHITE}:"  # 38→48
        f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
    )
    y_pos += 70

    # 営業時間
    for i, line in enumerate(hours_lines):
        esc = escape_ffmpeg_text(line.strip())
        if not esc:
            continue
        alpha, slide = make_slide_up_alpha(1.0 + i * 0.1, 0.4)
        elements.append(
            f"drawtext=text='{esc}':"
            f"fontfile='{font}':fontsize=26:fontcolor=#{COLOR_GRAY}:"  # 20→26
            f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
        )
        y_pos += 34
    y_pos += 34

    # 予約案内
    for i, line in enumerate(reservation_lines):
        esc = escape_ffmpeg_text(line.strip())
        if not esc:
            continue
        size = 44 if i == 0 else 58  # 36→44, TableCheck 48→58
        color = COLOR_GOLD if i == 0 else COLOR_WHITE
        alpha, slide = make_slide_up_alpha(1.3 + i * 0.15, 0.5)
        elements.append(
            f"drawtext=text='{esc}':"
            f"fontfile='{font}':fontsize={size}:fontcolor=#{color}:"
            f"x=(w-text_w)/2:y={y_pos}+({slide}):alpha={alpha}"
        )
        y_pos += size + 14

    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"eq=brightness={brightness},"
        + ",".join(elements)
    )

    args = [
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        output_path
    ]
    return run_ffmpeg(args, f"エンディング: {output_path}")


def concatenate_videos(clip_paths, output_path):
    """複数の動画を結合してリール動画を生成する"""
    # concat用テキストファイルを作成
    list_path = output_path + ".txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    args = [
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path
    ]
    result = run_ffmpeg(args, f"結合: {output_path}")
    os.remove(list_path)
    return result


# ============================================================
# メイン処理
# ============================================================

def generate_course(menu, course_id, lang, base_dir):
    """1つのコース × 1つの言語の動画を全て生成する"""
    course = menu["courses"][course_id]
    store = menu["store"]
    out_key = (course_id, lang)
    out_dir_name = OUTPUT_DIRS.get(out_key, f"output_{course_id}_{lang}")
    out_dir = os.path.join(base_dir, out_dir_name)
    os.makedirs(out_dir, exist_ok=True)

    # コースごとのタイミング・明るさを取得
    timing = COURSE_TIMING.get(course_id, COURSE_TIMING["seiran"])
    t_title = timing["title"]
    t_clip = timing["clip"]
    t_ending = timing["ending"]
    b_title = timing.get("title_brightness", -0.08)
    b_ending = timing.get("ending_brightness", -0.15)

    lang_name = LANG_NAMES.get(lang, lang)
    course_ja = COURSE_NAMES.get(course_id, course_id)
    print(f"\n{'='*50}")
    print(f"  {course_ja}コース × {lang_name} ({lang})")
    print(f"  出力先: {out_dir_name}/")
    print(f"  タイミング: title={t_title}s, clip={t_clip}s, ending={t_ending}s")
    print(f"{'='*50}")

    clip_paths = []

    # 1. タイトル
    print(f"  [1/13] タイトル生成中...")
    title_path = os.path.join(out_dir, "00_title.mp4")
    title_image = os.path.join(base_dir, course["title_image"])
    store_name = store["name"].get(lang, store["name"]["en"])
    course_name = course["name"].get(lang, course["name"]["en"])
    price = course["price"]

    if not os.path.exists(title_image):
        print(f"  [SKIP] 画像が見つかりません: {title_image}")
        return False

    if not generate_title(title_image, store_name, course_name, price, lang, title_path, duration=t_title, brightness=b_title):
        return False
    clip_paths.append(title_path)

    # 2. 料理クリップ（10本）
    for i, dish in enumerate(course["dishes"]):
        clip_num = i + 1
        print(f"  [{clip_num+1}/13] クリップ {clip_num:02d} 生成中...")
        clip_path = os.path.join(out_dir, f"{clip_num:02d}_clip.mp4")
        image = os.path.join(base_dir, dish["image"])

        if not os.path.exists(image):
            print(f"  [SKIP] 画像が見つかりません: {image}")
            continue

        category = dish["category"].get(lang, dish["category"].get("en", ""))
        description = dish["description"].get(lang, dish["description"].get("en", ""))
        is_summary = dish.get("category_is_course_summary", False)

        if not generate_clip(image, category, description, lang, clip_path, is_summary, duration=t_clip):
            return False
        clip_paths.append(clip_path)

    # 3. エンディング
    print(f"  [12/13] エンディング生成中...")
    ending_path = os.path.join(out_dir, "11_ending.mp4")
    ending_image = os.path.join(base_dir, course["ending_image"])

    if not generate_ending(ending_image, store, lang, ending_path, duration=t_ending, brightness=b_ending):
        return False
    clip_paths.append(ending_path)

    # 4. 結合
    print(f"  [13/13] リール動画を結合中...")
    reel_name = f"okurano_{course_id}_{lang}_reel.mp4"
    if lang == "ja":
        if course_id == "seiran":
            reel_name = "okurano_reel.mp4"
        else:
            reel_name = f"okurano_{course_id}_reel.mp4"
    reel_path = os.path.join(out_dir, reel_name)

    if not concatenate_videos(clip_paths, reel_path):
        return False

    # クリップの合計サイズを表示
    total_size = sum(os.path.getsize(p) for p in clip_paths if os.path.exists(p))
    reel_size = os.path.getsize(reel_path) if os.path.exists(reel_path) else 0
    print(f"  完了! リール: {reel_size/1024/1024:.1f}MB (クリップ合計: {total_size/1024/1024:.1f}MB)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="大嵓埜 多言語動画自動生成スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python generator/generate.py                           全言語・全コース生成
  python generator/generate.py --lang ja                 日本語のみ
  python generator/generate.py --lang en --lang ko       英語と韓国語
  python generator/generate.py --course seiran           青藍色コースのみ
  python generator/generate.py --lang fr --course kikyou フランス語・桔梗色のみ
        """
    )
    parser.add_argument("--lang", action="append", help="生成する言語（複数指定可）")
    parser.add_argument("--course", action="append", help="生成するコース: seiran / kikyou（複数指定可）")
    parser.add_argument("--list", action="store_true", help="対応言語の一覧を表示")
    parser.add_argument("--menu", default=None, help="メニューJSONファイルのパス（デフォルト: generator/menu.json）")

    args = parser.parse_args()

    # 言語一覧表示
    if args.list:
        print("\n対応言語一覧:")
        print("-" * 40)
        for code, name in LANG_NAMES.items():
            print(f"  {code:8s}  {name}")
        print(f"\n合計: {len(LANG_NAMES)} 言語")
        print(f"コース: {', '.join(f'{v}({k})' for k, v in COURSE_NAMES.items())}")
        return

    # プロジェクトルートを特定
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    # メニューファイル読み込み
    menu_path = args.menu or os.path.join(script_dir, "menu.json")
    if not os.path.exists(menu_path):
        print(f"エラー: メニューファイルが見つかりません: {menu_path}")
        sys.exit(1)

    with open(menu_path, "r", encoding="utf-8") as f:
        menu = json.load(f)

    print(f"\n大嵓埜 多言語動画生成システム")
    print(f"メニュー: {menu.get('month', '不明')} 月")

    # 生成対象の決定
    languages = args.lang or ALL_LANGUAGES
    courses = args.course or ALL_COURSES

    # バリデーション
    for lang in languages:
        if lang not in LANG_NAMES:
            print(f"エラー: 未対応の言語コード '{lang}'")
            print(f"対応言語: {', '.join(ALL_LANGUAGES)}")
            sys.exit(1)
    for course in courses:
        if course not in ALL_COURSES:
            print(f"エラー: 未対応のコース '{course}'")
            print(f"対応コース: {', '.join(ALL_COURSES)}")
            sys.exit(1)

    total = len(languages) * len(courses)
    print(f"生成予定: {len(languages)} 言語 × {len(courses)} コース = {total} パターン")
    print(f"言語: {', '.join(LANG_NAMES[l] for l in languages)}")
    print(f"コース: {', '.join(COURSE_NAMES[c] for c in courses)}")

    # FFmpeg確認
    if not shutil.which("ffmpeg"):
        print("エラー: ffmpegがインストールされていません")
        sys.exit(1)

    # 生成実行
    success = 0
    fail = 0
    for course_id in courses:
        for lang in languages:
            if generate_course(menu, course_id, lang, base_dir):
                success += 1
            else:
                fail += 1

    # 結果サマリー
    print(f"\n{'='*50}")
    print(f"  生成完了!")
    print(f"  成功: {success}/{total}  失敗: {fail}/{total}")
    print(f"{'='*50}\n")

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
