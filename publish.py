"""Publish Rewind to GitHub in one go.

    python publish.py            (or double-click publish.bat)

What it does:
  1. Creates the GitHub repo (first time only) and uploads this folder to it.
  2. Turns on the website (GitHub Pages, from the docs folder).
  3. Tags the version from app.py (v1.0.0 ...). That starts the cloud build, which
     makes Rewind.exe and publishes it as a Release the website's Download button points to.
  4. Waits for the build and tells you when the download is live.

To ship an update later: change VERSION in app.py (e.g. "1.0.1") and run this again.
The app shows "Get v1.0.1" to everyone on an older version.

Uses only the Python standard library.
"""
import argparse
import base64
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = os.environ.get("GITHUB_API", "https://api.github.com")
CONF = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "Rewind" / "publish.json"
TOKEN_URL = "https://github.com/settings/tokens/new?scopes=repo,workflow&description=Rewind%20publisher"
SKIP_DIRS = {".git", "dist", "build", "__pycache__", ".venv", "venv", "output"}
SKIP_FILES = {"publish.json"}
SKIP_EXT = {".spec", ".pyc", ".log", ".mp4", ".ts"}


class GitHubError(Exception):
    pass


def call(method, path, token, body=None, ok404=False):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Rewind-publisher",
        **({"Content-Type": "application/json"} if data else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return (json.loads(raw) if raw else {}), r.headers
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404:
            return None, e.headers
        try:
            msg = json.loads(e.read()).get("message", "")
        except Exception:
            msg = ""
        raise GitHubError(f"{method} {path} failed ({e.code}): {msg}") from None


def say(msg=""):
    print(msg, flush=True)


def get_token(args):
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"], False
    try:
        saved = json.loads(CONF.read_text(encoding="utf-8")).get("token")
        if saved and not args.new_token:
            return saved, False
    except Exception:
        pass
    say("Rewind needs a GitHub token to publish for you (you only do this once).")
    say("A GitHub page is opening with the right boxes already ticked (repo, workflow).")
    say("Scroll down, press 'Generate token', copy it, and paste it here.")
    say(f"  {TOKEN_URL}")
    webbrowser.open(TOKEN_URL)
    tok = getpass.getpass("Token (hidden as you paste): ").strip()
    if not tok:
        sys.exit("No token entered.")
    return tok, True


def collect_files():
    files = {}
    for p in sorted(HERE.rglob("*")):
        rel = p.relative_to(HERE)
        if p.is_dir() or any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.name in SKIP_FILES or p.suffix.lower() in SKIP_EXT or p.stat().st_size > 45_000_000:
            continue
        files[rel.as_posix()] = p.read_bytes()
    return files


def main():
    ap = argparse.ArgumentParser(description="Publish Rewind to GitHub.")
    ap.add_argument("--repo", default="rewind", help="repo name (default: rewind)")
    ap.add_argument("--no-wait", action="store_true", help="don't wait for the exe build")
    ap.add_argument("--new-token", action="store_true", help="ask for a token again")
    args = ap.parse_args()

    m = re.search(r'^VERSION\s*=\s*"([\d.]+)"', (HERE / "app.py").read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit("Couldn't find VERSION in app.py.")
    version = m.group(1)
    tag = f"v{version}"

    token, fresh = get_token(args)
    try:
        me, headers = call("GET", "/user", token)
    except GitHubError as e:
        sys.exit(f"GitHub didn't accept that token ({e}). Run again with --new-token.")
    login = me["login"]
    scopes = headers.get("X-OAuth-Scopes")
    if scopes is not None and not {"repo", "workflow"} <= {s.strip() for s in scopes.split(",")}:
        say(f"Warning: this token has scopes '{scopes}'. It needs 'repo' and 'workflow'.")
    if fresh and input("Remember this token on this PC for next time? [Y/n] ").strip().lower() != "n":
        CONF.parent.mkdir(parents=True, exist_ok=True)
        CONF.write_text(json.dumps({"token": token}), encoding="utf-8")
    full = f"{login}/{args.repo}"
    site = f"https://{login.lower()}.github.io/{args.repo}/"
    say(f"\nPublishing Rewind {tag} as {full}")

    # 1. repo
    repo, _ = call("GET", f"/repos/{full}", token, ok404=True)
    if repo is None:
        say("  Creating the repo…")
        repo, _ = call("POST", "/user/repos", token, {
            "name": args.repo, "description": "Instant replay for your PC. Press Alt + F8, get the last 30 seconds as a clip.",
            "homepage": site, "auto_init": True, "has_wiki": False, "private": False})
    branch = repo.get("default_branch") or "main"

    # 2. upload everything as one commit
    (HERE / "repo.json").write_text(json.dumps({"repo": full}) + "\n", encoding="utf-8")
    files = collect_files()
    if "docs/index.html" in files:
        files["docs/index.html"] = files["docs/index.html"].replace(b"__REPO__", full.encode())
    ref = None
    for _ in range(10):  # a brand-new repo takes a moment to get its first commit
        ref, _ = call("GET", f"/repos/{full}/git/ref/heads/{branch}", token, ok404=True)
        if ref:
            break
        time.sleep(2)
    if not ref:
        raise GitHubError("The repo has no branch yet. Wait a minute and run again.")
    head = ref["object"]["sha"]
    head_commit, _ = call("GET", f"/repos/{full}/git/commits/{head}", token)
    say(f"  Uploading {len(files)} files…")
    tree = []
    for path, data in files.items():
        blob, _ = call("POST", f"/repos/{full}/git/blobs", token,
                       {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        mode = "100755" if path.endswith((".bat", ".sh")) else "100644"
        tree.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})
    new_tree, _ = call("POST", f"/repos/{full}/git/trees", token, {"tree": tree})
    if new_tree["sha"] == head_commit["tree"]["sha"]:
        say("  Files are already up to date.")
        commit_sha = head
    else:
        commit, _ = call("POST", f"/repos/{full}/git/commits", token,
                         {"message": f"Rewind {tag}", "tree": new_tree["sha"], "parents": [head]})
        call("PATCH", f"/repos/{full}/git/refs/heads/{branch}", token, {"sha": commit["sha"], "force": False})
        commit_sha = commit["sha"]
        say("  Uploaded.")

    # 3. website
    pages, _ = call("GET", f"/repos/{full}/pages", token, ok404=True)
    if pages is None:
        try:
            call("POST", f"/repos/{full}/pages", token, {"source": {"branch": branch, "path": "/docs"}})
            say("  Website turned on (it takes a minute or two to appear the first time).")
        except GitHubError as e:
            say(f"  Couldn't turn on the website automatically ({e}).")
            say(f"  Do it by hand: {repo['html_url']}/settings/pages → Branch: {branch}, folder: /docs → Save.")
    else:
        say("  Website is on. It updates by itself after each upload.")

    # 4. release tag → cloud build
    existing, _ = call("GET", f"/repos/{full}/git/ref/tags/{tag}", token, ok404=True)
    if existing:
        say(f"\n{tag} is already released, so no new build was started.")
        say("To ship an update, change VERSION in app.py (for example to the next number) and run this again.")
        say(f"\nWebsite:  {site}\nRepo:     {repo['html_url']}")
        return
    call("POST", f"/repos/{full}/git/refs", token, {"ref": f"refs/tags/{tag}", "sha": commit_sha})
    say(f"  Tagged {tag}. The exe is now building in the cloud.")
    actions = f"{repo['html_url']}/actions"
    if args.no_wait:
        say(f"\nWatch the build: {actions}\nWebsite: {site}")
        return

    # 5. wait for the build
    say("\nWaiting for the build (usually 4–8 minutes). You can close this window; it keeps going in the cloud.")
    run, start, last = None, time.time(), ""
    while time.time() - start < 30 * 60:
        time.sleep(15)
        runs, _ = call("GET", f"/repos/{full}/actions/runs?per_page=10", token)
        for r in runs.get("workflow_runs", []):
            if r.get("head_branch") == tag or r.get("head_sha") == commit_sha:
                run = r
                break
        if not run:
            say("  waiting for the build to start…")
            continue
        status = run["status"] if run["status"] != "completed" else run["conclusion"]
        if status != last:
            say(f"  build: {status.replace('_', ' ')}")
            last = status
        if run["status"] == "completed":
            break
        run = None if run["status"] != "completed" else run
    if run and run.get("conclusion") == "success":
        say(f"\nDone. Rewind {tag} is live.")
        say(f"  Website:   {site}")
        say(f"  Download:  {repo['html_url']}/releases/latest/download/Rewind-windows.zip")
        webbrowser.open(site)
    elif run:
        say(f"\nThe build failed. Open it, click the red step, and paste the error to Claude:\n  {run['html_url']}")
    else:
        say(f"\nThe build is still going. Check it here: {actions}")


if __name__ == "__main__":
    try:
        main()
    except GitHubError as e:
        sys.exit(f"\nStopped: {e}")
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
