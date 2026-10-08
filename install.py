#!/usr/bin/env python3
"""Install Safety Rails into a project:  python3 install.py /path/to/project

Copies the hooks into <project>/.claude/hooks/ and merges the rules into
<project>/.claude/settings.json. Existing settings are kept and backed up first.
Run it again any time; it never adds the same rule twice.
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = ["guard_bash.py", "guard_files.py", "checkpoint.py"]


def merge(settings, rails):
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    deny.extend(rule for rule in rails["permissions"]["deny"] if rule not in deny)
    hooks = settings.setdefault("hooks", {})
    for event, groups in rails["hooks"].items():
        existing = hooks.setdefault(event, [])
        for group in groups:
            if group not in existing:
                existing.append(group)
    return settings


def install(project):
    claude_dir = os.path.join(project, ".claude")
    os.makedirs(os.path.join(claude_dir, "hooks"), exist_ok=True)
    for name in HOOKS:
        target = os.path.join(claude_dir, "hooks", name)
        shutil.copy(os.path.join(HERE, ".claude", "hooks", name), target)
        os.chmod(target, 0o755)
    settings_path = os.path.join(claude_dir, "settings.json")
    settings = {}
    if os.path.exists(settings_path):
        backup = f"{settings_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy(settings_path, backup)
        print(f"Backed up existing settings to {backup}")
        with open(settings_path, encoding="utf-8") as handle:
            settings = json.load(handle)
    with open(os.path.join(HERE, ".claude", "safety-rails.settings.json"), encoding="utf-8") as handle:
        rails = json.load(handle)
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(merge(settings, rails), handle, indent=2)
        handle.write("\n")
    print(f"Safety Rails installed in {claude_dir}. Restart Claude Code, then run /hooks to confirm.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("Usage: python3 install.py /path/to/project")
    install(os.path.abspath(sys.argv[1]))
