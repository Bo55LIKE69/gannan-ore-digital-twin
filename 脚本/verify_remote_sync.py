# -*- coding: utf-8 -*-
"""校验 GitHub 远端 main 的文件内容是否与本地工作区逐字节一致。
用 Git Data API 拿远端 tree，逐个 blob 与本地 git hash-object 比对。
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Bo55LIKE69/gannan-ore-digital-twin"
API = "https://api.github.com/repos/" + REPO


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True,
                          cwd=ROOT).stdout.decode("utf-8", "replace")


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


def api(path):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "sync-verify",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    ref = api("/git/refs/heads/main")
    sha = ref["object"]["sha"]
    print("远端 main @ %s\n" % sha[:10])

    tree = api("/git/trees/" + sha + "?recursive=1")
    remote = {}
    for e in tree["tree"]:
        if e["type"] == "blob":
            remote[e["path"]] = e["sha"]

    print("远端 blob %d 个" % len(remote))

    # 本地 tracked 文件
    tracked = set(f for f in git("ls-files").splitlines() if f)
    print("本地 tracked %d 个\n" % len(tracked))

    diff = []
    missing_local = []
    extra_local = []

    for path, rsha in sorted(remote.items()):
        full = os.path.join(ROOT, path.replace("/", os.sep))
        if not os.path.isfile(full):
            missing_local.append(path)
            continue
        # git blob sha1 = sha1("blob <len>\0" + content)
        with open(full, "rb") as f:
            data = f.read()
        lsha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if lsha != rsha:
            diff.append(path)

    for f in sorted(tracked):
        if f not in remote:
            extra_local.append(f)

    print("=== 结果 ===")
    print("内容不一致: %d" % len(diff))
    for p in diff:
        print("   ✗", p)
    print("远端有/本地无: %d" % len(missing_local))
    for p in missing_local:
        print("   -", p)
    print("本地 tracked/远端无: %d" % len(extra_local))
    for p in extra_local:
        print("   +", p)

    ok = not diff and not missing_local and not extra_local
    print("\n%s" % ("✅ 远端与本地完全一致" % () if ok else "⚠️ 存在差异，见上"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
