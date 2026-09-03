# -*- coding: utf-8 -*-
"""用 GitHub Contents API 增量提交少量文件（git push 被代理 502 时的轻量兜底）。

用法：python 脚本/put_files.py <相对路径> [<相对路径> ...]
特点：逐文件 PUT，父提交直接取远端 main，历史线性追加，不会重建整棵树。
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Bo55LIKE69/gannan-ore-digital-twin"
API = "https://api.github.com/repos/" + REPO


def get_token():
    p = subprocess.run(["git", "credential-manager", "get"], capture_output=True,
                       cwd=ROOT, input=b"protocol=https\nhost=github.com\n\n")
    for line in p.stdout.decode().splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    sys.exit("❌ 拿不到 GitHub token")


TOKEN = get_token()

# 代理（Python urllib 默认不读 http_proxy env，必须显式挂上）
_PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
if _PROXY:
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({"http": _PROXY, "https": _PROXY})))


def api(method, path, payload=None, allow_404=False):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "put-files",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        sys.exit("❌ API %s %s 失败 %s: %s" % (method, path, e.code,
                                               e.read().decode()[:300]))


def put_file(rel, message):
    full = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(full):
        print("  ⚠ 跳过（不存在）", rel)
        return None
    with open(full, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    path = "/contents/" + urllib.parse.quote(rel)
    cur = api("GET", path, allow_404=True)
    payload = {"message": message, "content": content, "branch": "main"}
    if cur and cur.get("sha"):
        payload["sha"] = cur["sha"]
        action = "更新"
    else:
        action = "新增"
    res = api("PUT", path, payload)
    print("  ✅ %s %s → %s" % (action, rel, res["commit"]["sha"][:10]))
    return res["commit"]["sha"]


def main():
    files = sys.argv[1:]
    if not files:
        sys.exit("用法: python 脚本/put_files.py <文件> [...]")
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"],
                         capture_output=True, cwd=ROOT).stdout.decode().strip()
    print("提交信息: %s\n" % msg.splitlines()[0])
    for f in files:
        put_file(f, msg)
    head = api("GET", "/git/refs/heads/main")
    print("\n远端 main 现在 @ %s" % head["object"]["sha"][:10])


if __name__ == "__main__":
    main()
