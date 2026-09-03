# -*- coding: utf-8 -*-
"""用 Git Data API 把若干文件打成**一个** commit 推到远端 main。

与 sync_to_github.py 的区别：
- 那个是全量重建（几十个文件，慢）
- 这个是增量，且显式指定 parent，可用来「回退 + 重提」整理历史
  （例如把远端 3 个重复 message 的 commit 压成 1 个）

用法：
    python 脚本/push_commit_api.py <parent_sha> "<commit message>" <file> [<file> ...]

例：
    python 脚本/push_commit_api.py 45a55e1 "tools: ..." 脚本/a.py 脚本/b.py
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


def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "push-commit-api",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit("❌ API %s %s 失败 %s:\n%s" % (method, path, e.code,
                                                e.read().decode()[:400]))


def upload_blob(rel):
    full = os.path.join(ROOT, rel.replace("/", os.sep))
    with open(full, "rb") as f:
        content = f.read()
    # 二进制安全：用 base64 编码上传
    res = api("POST", "/git/blobs",
              {"encoding": "base64",
               "content": base64.b64encode(content).decode()})
    return res["sha"]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    parent = sys.argv[1]
    message = sys.argv[2]
    files = sys.argv[3:]

    print("parent = %s" % parent[:10])
    print("文件 %d 个: %s\n" % (len(files), ", ".join(files)))

    # 1) parent 的 tree
    parent_commit = api("GET", "/git/commits/" + parent)
    base_tree = parent_commit["tree"]["sha"]

    # 2) blobs
    items = []
    for i, f in enumerate(files, 1):
        sha = upload_blob(f)
        items.append({"path": f, "mode": "100644", "type": "blob", "sha": sha})
        print("  %d/%d %s" % (i, len(files), f))

    # 3) tree + commit
    tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": items})
    commit = api("POST", "/git/commits",
                 {"message": message, "tree": tree["sha"], "parents": [parent]})
    new_sha = commit["sha"]
    print("\n新 commit @ %s" % new_sha[:10])

    # 4) 移动 ref（force 允许回退）
    api("PATCH", "/git/refs/heads/main", {"sha": new_sha, "force": True})
    print("✅ 远端 main -> %s" % new_sha[:10])


if __name__ == "__main__":
    main()
