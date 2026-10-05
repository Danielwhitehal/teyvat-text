# -*- coding: utf-8 -*-
"""本地查看器启动器（跨平台）：起 HTTP 服务并打开 web/quest_tree.html。

查看器在运行时用 fetch 读取 data/ 下的 JSON，浏览器在 file:// 下会拦截，
因此必须经 HTTP 服务打开，不能直接双击 HTML。

用法：
    python serve.py               # 默认 http://localhost:8000/web/quest_tree.html
    python serve.py --port 8001   # 换端口
"""
import argparse
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGE = "web/quest_tree.html"


def main():
    ap = argparse.ArgumentParser(description="启动原神文本查看器")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    if not (ROOT / PAGE).exists():
        print(f"找不到 {PAGE}，请先运行: python tools/generate_html_v2.py")
        return 1

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as e:
        print(f"端口 {args.port} 无法使用：{e}\n可换端口重试：python serve.py --port 8001")
        return 1

    url = f"http://localhost:{args.port}/{PAGE}"
    print(f"服务根：{ROOT}")
    print(f"打开：{url}")
    print("（Ctrl+C 停止）")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
