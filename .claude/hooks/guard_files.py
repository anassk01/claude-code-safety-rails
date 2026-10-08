#!/usr/bin/env python3
"""Safety Rails: PreToolUse guard for Write/Edit/MultiEdit/NotebookEdit.

Denies edits outside the project (plus the temp folder and SAFETY_RAILS_ALLOW_PATHS), and asks
before touching secrets or git internals.
"""
import json
import os
import re
import sys
import tempfile

PROTECTED = [
    (r"(^|/)\.git/", "deny", "edits git internals"),
    (r"(^|/)\.env(\.[\w.-]+)?$", "ask", "edits an environment/secrets file"),
    (r"\.(pem|key|p12|pfx)$|(^|/)id_(rsa|ed25519|ecdsa)", "deny", "edits a private key"),
    (r"(^|/)\.claude/(settings(\.local)?\.json|hooks/)", "ask", "changes the agent's own safety settings"),
]


def decide(file_path, project_dir):
    if not file_path:
        return None
    root = os.path.realpath(project_dir)
    path = os.path.realpath(os.path.join(project_dir, os.path.expanduser(file_path)))
    allowed = [root, os.path.realpath(tempfile.gettempdir())] + [
        os.path.realpath(p) for p in os.environ.get("SAFETY_RAILS_ALLOW_PATHS", "").split(os.pathsep) if p
    ]
    if not any(path == base or path.startswith(base + os.sep) for base in allowed):
        return "deny", f"writes outside the project ({file_path})"
    relative = os.path.relpath(path, root).replace(os.sep, "/")
    for pattern, decision, reason in PROTECTED:
        if re.search(pattern, relative):
            return decision, f"{reason} ({relative})"
    return None


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    verdict = decide(file_path, project_dir)
    if verdict:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": verdict[0],
            "permissionDecisionReason": f"Safety Rails: {verdict[1]}.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
