# Safety Rails for Claude Code

Stop the "Claude deleted my project" moment before it happens.

Safety Rails is three small hooks and a set of deny rules. They run before Claude Code touches
your shell or files. Catastrophic commands are **blocked**, risky ones **ask you first**, and your
work is **checkpointed** before every prompt so you can roll back.

Not affiliated with or endorsed by Anthropic. "Claude Code" is used only to say what this works
with.

## Install (2 minutes)

Requirements: Claude Code, Python 3.8+, git (git is only needed for checkpoints).

```bash
python3 selftest.py                      # proves every rule on your machine, deletes nothing
python3 install.py /path/to/your/project
```

Restart Claude Code in that project and run `/hooks`. You should see the Safety Rails hooks.

`install.py` keeps your existing `.claude/settings.json`, backs it up first, and never adds a rule
twice.

## What it does

**Blocked (deny)**
- `rm`, `rmdir`, `shred`, or `find -delete` on `/`, your home folder, the project root, `.git`,
  or anything outside the project. It follows `cd` inside the same command (`cd / && rm -rf usr`).
- Disk formatting and raw writes: `mkfs`, `dd of=/dev/…`, `wipefs`, partition tools.
- Windows drive wipes: `Remove-Item -Recurse C:\`, `rd /s C:\`, `format C:`.
- `chmod -R` / `chown -R` on `/` or your home folder.
- File writes outside the project (temp folder allowed), to `.git/` internals, or to private keys.
- Claude reading `.env`, `*.pem`, `*.key`, `~/.ssh`, and `~/.aws` (deny rules).

**Asks you first**
- `rm` whose target uses a variable (`rm -rf "$DIR/"` becomes `rm -rf /` if `$DIR` is empty), and
  `rm -rf *` at the project root.
- `git push --force` (use `--force-with-lease`), `reset --hard`, `clean -f`, `checkout -- .`,
  `stash drop`, `branch -D`.
- `DROP TABLE`, `TRUNCATE`, `DELETE FROM x` without `WHERE`.
- `curl … | sh`, `terraform destroy`, `kubectl delete`, `aws s3 rm --recursive`, `gh repo delete`.
- Inline code that deletes files (`shutil.rmtree`, `fs.rmSync`, …).
- Edits to `.env` files or to Claude's own `.claude/settings.json` and hooks.

**Allowed without friction:** everyday work such as `rm -rf node_modules`, deleting files inside
the project, `git push --force-with-lease`, and running tests.

**Checkpoints:** before each prompt, the current files (tracked and untracked, respecting
`.gitignore`) are saved as a hidden git commit under `refs/safety-rails/`. Your branch, staging
area, and files are never touched. The last 50 are kept. See `RECOVERY.md`.

## Customize

- **Allow another folder** (for example a shared data folder):
  `export SAFETY_RAILS_ALLOW_PATHS=/data/shared:/mnt/scratch`
- **Change a rule:** edit `PATTERNS` in `.claude/hooks/guard_bash.py`. Use `"deny"` to block or
  `"ask"` to prompt. Run `python3 selftest.py` afterwards.
- **Use it in every project:** run `install.py` per project. Rules live with the project, so
  teammates get them through git.

## How it fits with other options

Use layers, not one tool:

- **Claude Code's sandbox** (`/sandbox`, [docs](https://code.claude.com/docs/en/sandboxing)) isolates
  the filesystem at the OS level on macOS, Linux, and WSL2. That's the strongest layer, so turn it on.
  Safety Rails adds what a sandbox doesn't: *asking* before `git push --force` or `DROP TABLE`, which
  are allowed writes, and automatic restore points.
- **[Destructive Command Guard](https://github.com/Dicklesworthstone/destructive_command_guard)** is
  a larger Rust hook with many more command patterns. Prefer it if you want maximum coverage of
  shell commands.
- **Safety Rails** is small plain Python you can read in 10 minutes and edit. It adds file-write
  guards, secret-read deny rules, git-based checkpoints, and a self-test that proves each rule.

## Honest limits

Safety Rails is a seatbelt, not a sandbox. Pattern checks catch the common destructive commands,
but a determined or unusual script (for example deletion code written to a file and then run) can
get past them. For untrusted work, also use Claude Code's sandbox or a container, and keep real
backups. Checkpoints live inside `.git`, so they don't survive deleting the repository itself.
That's why deleting the project root and `.git` is blocked.

## Files

| File | Purpose |
|---|---|
| `.claude/hooks/guard_bash.py` | Shell command guard |
| `.claude/hooks/guard_files.py` | File write/edit guard |
| `.claude/hooks/checkpoint.py` | Automatic snapshots + `--list` / `--restore` |
| `.claude/safety-rails.settings.json` | Hook wiring and deny rules merged by the installer |
| `install.py` | Installer |
| `selftest.py` | Self-test with 36 checks |
| `RECOVERY.md` | What to do when something was already lost |

## License

MIT. Free to use, change, and share. Issues and pull requests are welcome.
