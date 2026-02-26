#!/usr/bin/env python3
"""
大嵓埜 管理画面サーバー

起動方法:
  python3 generator/server.py
  → ブラウザで http://localhost:8080 を開く

オプション:
  python3 generator/server.py --port 3000   ← ポート変更
"""

import http.server
import json
import os
import sys
import threading
import subprocess
import urllib.parse
import io
import re
import time
from pathlib import Path

# プロジェクトルート
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
MENU_PATH = os.path.join(SCRIPT_DIR, "menu.json")
ADMIN_HTML_PATH = os.path.join(SCRIPT_DIR, "admin.html")

# 動画生成状態
generation_state = {
    "status": "idle",       # idle / running / done / error
    "progress": 0,          # 0-100
    "current_task": "",
    "log": [],
    "started_at": None,
    "finished_at": None,
}
generation_lock = threading.Lock()


def read_menu():
    with open(MENU_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_menu(data):
    with open(MENU_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_images():
    """processed/ と processed2/ の画像一覧を返す"""
    images = []
    for d in ["processed", "processed2"]:
        dirpath = os.path.join(BASE_DIR, d)
        if not os.path.isdir(dirpath):
            continue
        for f in sorted(os.listdir(dirpath)):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                images.append(f"{d}/{f}")
    return images


def list_videos():
    """生成済みリール動画の一覧を返す"""
    videos = {}
    for entry in os.listdir(BASE_DIR):
        dirpath = os.path.join(BASE_DIR, entry)
        if not os.path.isdir(dirpath) or not entry.startswith("output"):
            continue
        for f in sorted(os.listdir(dirpath)):
            if f.endswith("_reel.mp4"):
                rel = f"{entry}/{f}"
                videos[rel] = {
                    "path": rel,
                    "size": os.path.getsize(os.path.join(dirpath, f)),
                    "dir": entry,
                }
    return videos


def run_generation(languages, courses):
    """バックグラウンドで動画生成を実行"""
    global generation_state

    with generation_lock:
        generation_state = {
            "status": "running",
            "progress": 0,
            "current_task": "準備中...",
            "log": [],
            "started_at": time.time(),
            "finished_at": None,
        }

    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "generate.py")]
    for lang in languages:
        cmd += ["--lang", lang]
    for course in courses:
        cmd += ["--course", course]

    total_tasks = len(languages) * len(courses)
    completed = 0

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=BASE_DIR
        )

        for line in proc.stdout:
            line = line.rstrip()
            with generation_lock:
                generation_state["log"].append(line)
                # 進捗パース
                if "出力先:" in line:
                    generation_state["current_task"] = line.strip()
                elif "完了!" in line and "リール:" in line:
                    completed += 1
                    generation_state["progress"] = int(completed / total_tasks * 100)
                elif line.strip().startswith("[") and "/13]" in line:
                    step = re.search(r'\[(\d+)/13\]', line)
                    if step:
                        step_num = int(step.group(1))
                        base_pct = int((completed / total_tasks) * 100)
                        step_pct = int((step_num / 13) * (100 / total_tasks))
                        generation_state["progress"] = min(99, base_pct + step_pct)

        proc.wait()

        with generation_lock:
            if proc.returncode == 0:
                generation_state["status"] = "done"
                generation_state["progress"] = 100
                generation_state["current_task"] = "全て完了"
            else:
                generation_state["status"] = "error"
                generation_state["current_task"] = "エラーが発生しました"
            generation_state["finished_at"] = time.time()

    except Exception as e:
        with generation_lock:
            generation_state["status"] = "error"
            generation_state["current_task"] = f"エラー: {str(e)}"
            generation_state["log"].append(f"Exception: {str(e)}")
            generation_state["finished_at"] = time.time()


class OkuranoHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # アクセスログを簡潔に
        if "/api/" in str(args[0]):
            return
        super().log_message(format, *args)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filepath, content_type=None):
        if not os.path.exists(filepath):
            self.send_error(404)
            return
        if content_type is None:
            ext = os.path.splitext(filepath)[1].lower()
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css",
                ".js": "application/javascript",
                ".json": "application/json",
                ".mp4": "video/mp4",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }.get(ext, "application/octet-stream")

        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", size)
        self.end_headers()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/admin":
            self.send_file(ADMIN_HTML_PATH)

        elif path == "/api/menu":
            self.send_json(read_menu())

        elif path == "/api/images":
            self.send_json(list_images())

        elif path == "/api/videos":
            self.send_json(list_videos())

        elif path == "/api/status":
            with generation_lock:
                self.send_json(generation_state)

        elif path.startswith("/files/"):
            # 静的ファイル配信（画像・動画）
            rel = path[7:]  # /files/ を除去
            filepath = os.path.normpath(os.path.join(BASE_DIR, rel))
            if not filepath.startswith(BASE_DIR):
                self.send_error(403)
                return
            self.send_file(filepath)

        else:
            # ルートからの静的ファイル
            filepath = os.path.normpath(os.path.join(BASE_DIR, path.lstrip("/")))
            if not filepath.startswith(BASE_DIR):
                self.send_error(403)
                return
            if os.path.isfile(filepath):
                self.send_file(filepath)
            else:
                self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        if path == "/api/menu":
            try:
                data = json.loads(body.decode("utf-8"))
                write_menu(data)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 400)

        elif path == "/api/generate":
            with generation_lock:
                if generation_state["status"] == "running":
                    self.send_json({"ok": False, "error": "生成中です"}, 409)
                    return

            try:
                params = json.loads(body.decode("utf-8"))
                languages = params.get("languages", [])
                courses = params.get("courses", [])
                if not languages or not courses:
                    self.send_json({"ok": False, "error": "言語とコースを選択してください"}, 400)
                    return

                thread = threading.Thread(
                    target=run_generation, args=(languages, courses), daemon=True
                )
                thread.start()
                self.send_json({"ok": True, "message": "生成を開始しました"})

            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 400)

        elif path == "/api/upload":
            # マルチパート画像アップロード
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_json({"ok": False, "error": "multipart required"}, 400)
                return
            try:
                boundary = content_type.split("boundary=")[1].strip()
                parts = body.split(f"--{boundary}".encode())
                for part in parts:
                    if b"filename=" not in part:
                        continue
                    header_end = part.find(b"\r\n\r\n")
                    if header_end < 0:
                        continue
                    header_text = part[:header_end].decode("utf-8", errors="replace")
                    file_data = part[header_end + 4:]
                    if file_data.endswith(b"\r\n"):
                        file_data = file_data[:-2]

                    # ファイル名取得
                    fn_match = re.search(r'filename="([^"]+)"', header_text)
                    if not fn_match:
                        continue
                    filename = os.path.basename(fn_match.group(1))

                    # 保存先決定
                    dest_match = re.search(r'name="([^"]+)"', header_text)
                    dest_dir = "processed"
                    if dest_match and dest_match.group(1) == "processed2":
                        dest_dir = "processed2"

                    dest_path = os.path.join(BASE_DIR, dest_dir, filename)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with open(dest_path, "wb") as f:
                        f.write(file_data)

                    self.send_json({"ok": True, "path": f"{dest_dir}/{filename}"})
                    return

                self.send_json({"ok": False, "error": "ファイルが見つかりません"}, 400)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 400)

        else:
            self.send_error(404)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="大嵓埜 管理画面サーバー")
    parser.add_argument("--port", type=int, default=8080, help="ポート番号（デフォルト: 8080）")
    args = parser.parse_args()

    server = http.server.HTTPServer(("0.0.0.0", args.port), OkuranoHandler)
    print(f"\n  大嵓埜 管理画面")
    print(f"  http://localhost:{args.port}/")
    print(f"  Ctrl+C で終了\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました")
        server.server_close()


if __name__ == "__main__":
    main()
