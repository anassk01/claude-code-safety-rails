#!/usr/bin/env python3
"""Safety Rails: snapshot the working tree before each prompt (UserPromptSubmit hook).

Stores tracked + untracked (non-ignored) files as a hidden git commit under
refs/safety-rails/. It never touches your index, branch, or working files.
Restore with:  python3 .claude/hooks/checkpoint.py --list | --restore <ref>
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

PREFIX = "refs/safety-rails/"
KEEP = 50


def git(*args, env=None, check=True):
    result = subprocess.run(["git", *args], capture_output=True, text=True, env=env, cwd=ROOT)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def snapshot():
    git_dir = git("rev-parse", "--git-dir")
    with tempfile.TemporaryDirectory() as tmp:
        index = os.path.join(tmp, "index")
        real_index = os.path.join(ROOT, git_dir, "index")
        if os.path.exists(real_index):
            shutil.copy(real_index, index)
        env = dict(os.environ, GIT_INDEX_FILE=index)
        git("add", "-A", env=env)
        tree = git("write-tree", env=env)
    refs = list_refs()
    if refs and git("rev-parse", refs[0] + "^{tree}") == tree:
        return None  # nothing changed since the last checkpoint
    head = git("rev-parse", "-q", "--verify", "HEAD", check=False)
    commit = git("commit-tree", tree, *(["-p", head] if head else []), "-m", "safety-rails checkpoint")
    ref = PREFIX + time.strftime("%Y%m%d-%H%M%S")
    git("update-ref", ref, commit)
    for old in list_refs()[KEEP:]:
        git("update-ref", "-d", old)
    return ref


def list_refs():
    out = git("for-each-ref", "--sort=-refname", "--format=%(refname)", PREFIX, check=False)
    return [line for line in out.splitlines() if line]


def restore(ref):
    if not ref.startswith(PREFIX):
        ref = PREFIX + ref
    git("restore", "--source", ref, "--worktree", "--", ".")
    print(f"Restored files from {ref}. Files created after it were left in place; review with `git status`.")


if __name__ == "__main__":
    ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--list":
            for item in list_refs():
                print(item, git("log", "-1", "--format=%cr", item))
        elif len(sys.argv) > 2 and sys.argv[1] == "--restore":
            restore(sys.argv[2])
        else:
            if git("rev-parse", "--is-inside-work-tree", check=False) == "true":
                snapshot()
    except Exception as exc:  # a checkpoint failure must never block the user's prompt
        print(f"Safety Rails checkpoint skipped: {exc}", file=sys.stderr)
    sys.exit(0)
