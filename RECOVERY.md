# Recovery runbook

Something got deleted or overwritten. Work through these steps in order. **Stop the agent first**
(press Esc, or close the session) so it doesn't "fix" things further.

## 1. Restore from a Safety Rails checkpoint (fastest)

```bash
cd /path/to/project
python3 .claude/hooks/checkpoint.py --list            # newest first, with age
python3 .claude/hooks/checkpoint.py --restore 20261008-142530
git status                                             # review what came back
```

Restore brings back every file as it was at that checkpoint. Files created after the checkpoint
are left in place. To restore just one file:

```bash
git restore --source refs/safety-rails/20261008-142530 -- path/to/file
```

## 2. Recover from git itself

- Uncommitted changes discarded by `reset --hard` or `checkout -- .`: try step 1 first. Staged
  content may still be found with `git fsck --lost-found`.
- Lost commits or a deleted branch: `git reflog`, then `git branch rescue <sha>`.
- A force-push overwrote the remote: another clone, CI cache, or a teammate's reflog still has the
  old commits. Run `git reflog` on any machine that pulled before the push.

## 3. Use Claude Code's own history

Claude Code keeps checkpoints of the file edits it made, but not of shell commands. Run `/rewind`
(or press Esc twice) to return to an earlier point in the conversation and code.

## 4. Outside the repository

Shell deletions bypass the trash. Check, in order: OS snapshots (Time Machine, Windows File
History, btrfs/ZFS snapshots), cloud sync version history (Dropbox, OneDrive, Google Drive), and
backups. On Linux, stop writing to the disk before trying recovery tools.

## 5. Prevent a repeat

- Read the denial reason the agent saw and add a stricter rule if needed (`guard_bash.py`).
- Commit more often. Checkpoints complement commits; they don't replace them.
- Run risky or unattended agent work in a sandbox or container.
