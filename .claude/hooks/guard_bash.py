#!/usr/bin/env python3
"""Safety Rails: PreToolUse guard for Bash commands.

Denies catastrophic commands and asks before risky ones. It is a seatbelt, not a sandbox:
pattern checks can be bypassed by unusual code, so keep backups and checkpoints too.
"""
import json
import os
import re
import shlex
import sys
import tempfile

DENY, ASK = "deny", "ask"

# (pattern, decision, reason). Checked against the whole command, case-insensitive.
PATTERNS = [
    (r"\bmkfs(\.\w+)?\b|\bwipefs\b|\b(fdisk|parted|sfdisk)\s+/dev/", DENY, "formats or repartitions a disk"),
    (r"\bdd\b[^|;&]*\bof=/dev/", DENY, "writes raw bytes to a device"),
    (r">\s*/dev/(sd|nvme|hd|disk)", DENY, "overwrites a disk device"),
    (r"\bchmod\s+-R\b[^|;&]*\s(/|~|\$HOME)(\s|$)|\bchown\s+-R\b[^|;&]*\s(/|~|\$HOME)(\s|$)", DENY, "changes permissions on the whole system or home folder"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", DENY, "fork bomb"),
    (r"\bformat\s+[a-z]:", DENY, "formats a Windows drive"),
    (r"\b(rd|rmdir)\s+/s\b[^|;&]*\s[a-z]:\\?(\s|$|\")|\bdel\s+/[sfq][^|;&]*\s[a-z]:\\", DENY, "deletes a Windows drive root"),
    (r"remove-item\b[^|;&]*-recurse[^|;&]*\s[a-z]:\\?(\s|$|['\"])", DENY, "deletes a Windows drive root"),
    (r"\b(rd|rmdir)\s+/s\b|\bdel\s+/s\b|remove-item\b[^|;&]*-recurse", ASK, "recursive delete on Windows"),
    (r"\bgit\s+push\b[^|;&]*(\s--force(?!-with-lease)\b|\s-f\b|\s\+\w)", ASK, "force-push rewrites remote history (prefer --force-with-lease)"),
    (r"\bgit\s+push\b[^|;&]*\s--mirror\b|\bgit\s+push\b[^|;&]*\s--delete\b", ASK, "deletes or overwrites remote refs"),
    (r"\bgit\s+reset\s+--hard\b", ASK, "discards uncommitted work"),
    (r"\bgit\s+clean\b[^|;&]*\s-\w*f", ASK, "deletes untracked files"),
    (r"\bgit\s+(checkout|restore)\b[^|;&]*\s(--\s+)?\.(\s|$)", ASK, "discards uncommitted changes"),
    (r"\bgit\s+stash\s+(drop|clear)\b|\bgit\s+branch\s+-D\b|\bgit\s+filter-(branch|repo)\b", ASK, "permanently drops git work"),
    (r"\b(drop\s+(database|schema|table)|truncate\s+table)\b", ASK, "destroys database data"),
    (r"\bdelete\s+from\s+\w+\s*(;|$|\")", ASK, "DELETE without WHERE removes every row"),
    (r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", ASK, "runs a downloaded script without review"),
    (r"\bterraform\s+destroy\b|\bkubectl\s+delete\b|\baws\s+s3\s+(rm|rb)\b[^|;&]*--recursive|\bgh\s+repo\s+delete\b", ASK, "destroys cloud or remote resources"),
    (r"\bshutil\.rmtree\b|\bos\.(remove|unlink|rmdir)\b|\bfs\.(rm|rmSync|rmdirSync)\b", ASK, "inline code deletes files"),
]

DELETE_TOOLS = {"rm", "rmdir", "unlink", "shred", "trash", "trash-put"}
WRAPPERS = {"sudo", "doas", "env", "nice", "nohup", "time", "command", "xargs"}


def decide(command, project_dir, cwd=None):
    cwd = cwd or project_dir
    worst = None
    for pattern, decision, reason in PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            if decision == DENY:
                return DENY, reason
            worst = worst or (ASK, reason)
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        cd = re.match(r"\s*(?:cd|pushd)\s+(\S+)\s*$", segment)
        if cd:  # follow `cd X && rm ...` so relative targets resolve where they really run
            cwd = os.path.join(cwd, os.path.expanduser(cd.group(1).strip("'\"")))
            continue
        result = _check_delete(segment, project_dir, cwd)
        if result and result[0] == DENY:
            return result
        worst = worst or result
    return worst


def _check_delete(segment, project_dir, cwd):
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        argv = segment.split()
    while argv and (argv[0] in WRAPPERS or "=" in argv[0]):
        argv = argv[1:]
    if not argv:
        return None
    tool = os.path.basename(argv[0])
    if tool == "find" and re.search(r"\s-delete\b|-exec\s+rm\b", segment):
        roots = [a for a in argv[1:] if not a.startswith("-")][:1] or ["."]
        return _judge_targets(roots, project_dir, cwd, "find -delete") or (ASK, "find -delete removes many files")
    if tool not in DELETE_TOOLS:
        return None
    targets = [a for a in argv[1:] if not a.startswith("-")]
    return _judge_targets(targets, project_dir, cwd, tool)


def _judge_targets(targets, project_dir, cwd, tool):
    root = os.path.realpath(project_dir)
    temp = os.path.realpath(tempfile.gettempdir())
    extra = [os.path.realpath(p) for p in os.environ.get("SAFETY_RAILS_ALLOW_PATHS", "").split(os.pathsep) if p]
    for target in targets:
        if "$" in target or "`" in target:
            return ASK, f"{tool} target uses a variable ({target}); an empty variable can delete '/'"
        path = os.path.realpath(os.path.join(cwd, os.path.expanduser(target)))
        if path in ("/", os.path.realpath(os.path.expanduser("~"))) or re.fullmatch(r"[A-Za-z]:\\?", target):
            return DENY, f"{tool} targets the filesystem root or home folder ({target})"
        if path == root or path == os.path.join(root, ".git") or path.startswith(os.path.join(root, ".git") + os.sep):
            return DENY, f"{tool} targets the project root or its .git history ({target})"
        inside = path.startswith(root + os.sep) or any(path == p or path.startswith(p + os.sep) for p in [temp] + extra)
        if not inside:
            return DENY, f"{tool} targets a path outside the project ({target})"
        if "*" in target and os.path.dirname(path) == root:
            return ASK, f"{tool} with a wildcard at the project root ({target})"
    return None


def main():
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    verdict = decide(command, project_dir, payload.get("cwd"))
    if verdict:
        decision, reason = verdict
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"Safety Rails: {reason}.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
