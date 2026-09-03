# -*- coding: utf-8 -*-
"""用 GitHub Git Data API 把本地 HEAD 一次性推到远端 main（代理 502 时的兜底通道）"""
import base64, io, json, os, subprocess, sys, urllib.request, urllib.error

REPO = "Bo55LIKE69/gannan-ore-digital-twin"
BASE = "02fe860"  # 远端 main 已知 SHA
API = "https://api.github.com/repos/" + REPO
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_token():
    out = subprocess.run(["git", "credential", "fill"], input=b"protocol=https\nhost=github.com\n",
                         capture_output=True).stdout.decode()
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("拿不到 GitHub token")


def api(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API + path, method=method, data=data)
    req.add_header("Authorization", "token " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit("HTTP %s %s\n%s" % (e.code, path, body[:600]))


def list_diff():
    """返回 (add_modify, delete) 列表，从 git diff --name-status 解析"""
    out = subprocess.run(["git", "diff", "--name-status", BASE, "HEAD"],
                         capture_output=True, cwd=ROOT, encoding="utf-8").stdout
    add_modify, delete = [], []
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        status, path = line.split("\t", 1)
        if status in ("A", "M"):
            add_modify.append(path)
        elif status == "D":
            delete.append(path)
    return add_modify, delete


def upload_blob(path):
    with io.open(os.path.join(ROOT, path), "rb") as f:
        content = f.read()
    # 大文件 > 50MB 用 git blob API 限制；这里最大就是工艺图 2MB 级别
    res = api("POST", "/git/blobs", {"encoding": "base64", "content": base64.b64encode(content).decode()})
    return res["sha"]


def main():
    global TOKEN
    TOKEN = get_token()

    add_modify, delete = list_diff()
    files = add_modify
    print("新增/修改 %d 个:" % len(files))
    for f in files:
        print("  +", f)
    print("删除 %d 个:" % len(delete))
    for f in delete:
        print("  -", f)

    # 1) 取远端 main 头
    main_ref = api("GET", "/git/refs/heads/main")
    parent_sha = main_ref["object"]["sha"]
    print("\n远端 main @ %s" % parent_sha[:10])

    # 2) 上传每个文件为 blob
    print("\n上传 blobs ...")
    tree_items = []
    for i, f in enumerate(files, 1):
        sha = upload_blob(f)
        tree_items.append({"path": f, "mode": "100644", "type": "blob", "sha": sha})
        print("  %2d/%d %s" % (i, len(files), f))

    # 3) 删除项
    deletions = [{"path": f, "mode": "100644", "type": "blob", "sha": None} for f in delete]

    # 3) 构造新 tree
    new_tree = api("POST", "/git/trees",
                   {"base_tree": api("GET", "/git/commits/" + parent_sha)["tree"]["sha"],
                    "tree": tree_items + deletions})

    # 4) 创建 commit
    new_commit = api("POST", "/git/commits", {
        "message": "chore: 同步本地 9 个 commit（浅色文档/AI学习指南/部署上线等）",
        "parents": [parent_sha],
        "tree": new_tree["sha"]
    })
    print("\n新 commit @ %s" % new_commit["sha"][:10])

    # 5) 更新 main ref
    api("PATCH", "/git/refs/heads/main", {"sha": new_commit["sha"], "force": False})
    print("\n✅ 远端 main 已更新")


if __name__ == "__main__":
    main()
