#!/usr/bin/env python3
"""Install the wiki-interest skill in one command (stdlib only, Python 3.10+).

  python install.py                     copy to ~/.claude/skills/wiki-interest + .venv + deps + doctor
  python install.py --project DIR       copy to DIR/.claude/skills/wiki-interest (skill for one project)
  python install.py --dest DIR          copy to any skills folder (other agents), DIR/wiki-interest
  python install.py --link              symlink instead of copy: edits in this repo apply at once
  python install.py --deps-only         only create .venv here and install dependencies
  python install.py --zip FILE.zip      build an archive to upload to claude.ai (Settings > Skills)
  python install.py claude haiku        install, then start Claude Code with that model
  python install.py claude haiku "..."  ... and send it the first request at once

Dependencies go into <skill>/.venv, so the system Python is not touched. The agent still
runs `python <skill>/scripts/wiki_interest.py ...`: the script switches to .venv by itself.
Re-running the installer updates the skill and keeps its data cache.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
import zipfile
from fnmatch import fnmatch
from pathlib import Path

SRC = Path(__file__).resolve().parent
NAME = SRC.name  # "wiki-interest"
KEEP_ON_UPDATE = {".cache", ".venv"}
SKIP = (".cache", ".venv", "__pycache__", "*.pyc", ".pytest_cache", "wiki-interest-output",
        "results", "*.zip")
IGNORE = shutil.ignore_patterns(*SKIP)


def venv_python(skill: Path) -> Path:
    win = skill / ".venv" / "Scripts" / "python.exe"
    return win if os.name == "nt" else skill / ".venv" / "bin" / "python"


def install_deps(skill: Path, system_python: bool) -> Path:
    if system_python:
        py = Path(sys.executable)
    else:
        py = venv_python(skill)
        if not py.exists():
            print(f"-> creating {skill / '.venv'}")
            venv.EnvBuilder(with_pip=True).create(skill / ".venv")
    print(f"-> installing {skill / 'requirements.txt'}")
    subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                    "-r", str(skill / "requirements.txt")], check=True)
    return py


def place(dest: Path, link: bool) -> None:
    if dest.resolve() == SRC:
        raise SystemExit(f"{dest} is the source folder itself; nothing to install")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    elif link and dest.exists():
        # a copy becomes a link: keep its data cache (the link shares SRC/.cache)
        keep_cache(dest / ".cache")
        shutil.rmtree(dest)
    if link:
        dest.symlink_to(SRC, target_is_directory=True)
        print(f"-> linked {dest} -> {SRC}")
        return
    if dest.exists():  # update: replace code, keep the data cache and .venv
        for child in dest.iterdir():
            if child.name not in KEEP_ON_UPDATE:
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(SRC, dest, ignore=IGNORE, dirs_exist_ok=True)
    print(f"-> copied to {dest}")


def keep_cache(cache: Path) -> None:
    """Move a copy's .cache to SRC/.cache, or next to the copy if SRC already has one."""
    if not cache.is_dir():
        return
    target = SRC / ".cache"
    if target.exists():
        target = cache.parent.parent / f"{NAME}-cache-backup"
    shutil.move(str(cache), str(target))
    print(f"-> kept the data cache: {target}")


def build_zip(out: Path) -> None:
    out = out.resolve()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.rglob("*")):
            rel = f.relative_to(SRC)
            if f.is_file() and not any(fnmatch(part, pat) for part in rel.parts for pat in SKIP):
                z.write(f, Path(NAME) / rel)
    print(f"-> {out}  (upload it in claude.ai: Settings > Capabilities > Skills)")


MODELS = {"haiku": "claude-haiku-4-5-20251001"}  # short names; anything else goes as is
CLAUDE_HINT = ("Claude Code is not installed. Install it (https://code.claude.com/docs), e.g.\n"
               "  curl -fsSL https://claude.ai/install.sh | bash\n"
               "then run this command again.")


def launch(agent: list[str], skill: Path, py: Path) -> int:
    """Start the agent in the current folder; .venv goes first in PATH, so `python` has the deps."""
    rest = agent[1:]
    exe = shutil.which("claude")
    if not exe:
        print(CLAUDE_HINT)
        return 1
    cmd = [exe]
    if rest:
        cmd += ["--model", MODELS.get(rest[0].lower(), rest[0])]
    cmd += rest[1:]  # optional first request
    env = dict(os.environ)
    if py.parent.parent.name == ".venv":
        env["PATH"] = str(py.parent) + os.pathsep + env.get("PATH", "")
    print(f"-> {' '.join(cmd)}")
    if os.name == "nt":
        return subprocess.run(cmd, env=env).returncode
    os.execve(exe, cmd, env)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    where = p.add_mutually_exclusive_group()
    where.add_argument("--project", type=Path, help="install for one project (its root folder)")
    where.add_argument("--dest", type=Path, help="skills folder of any agent")
    where.add_argument("--deps-only", action="store_true", help="only set up dependencies here")
    where.add_argument("--zip", type=Path, help="build an upload archive and exit")
    p.add_argument("--link", action="store_true", help="symlink instead of copy (development)")
    p.add_argument("--system-python", action="store_true",
                   help="pip install into the current Python instead of <skill>/.venv")
    p.add_argument("--no-doctor", action="store_true", help="skip the final self-check")
    p.add_argument("agent", nargs="*", metavar="claude [MODEL [REQUEST]]",
                   help="after installing, start Claude Code (MODEL: haiku, sonnet, opus or an id)")
    a = p.parse_args(argv)

    if a.agent and a.agent[0] != "claude":
        p.error(f"unknown agent {a.agent[0]!r}: only 'claude' is supported")
    if a.zip:
        if a.agent:
            p.error("--zip cannot be combined with starting an agent")
        build_zip(a.zip)
        return 0
    if a.deps_only:
        skill = SRC
    else:
        root = (a.dest if a.dest else
                a.project / ".claude" / "skills" if a.project else
                Path.home() / ".claude" / "skills")
        skill = root.expanduser().resolve() / NAME
        place(skill, a.link)
    py = install_deps(skill.resolve(), a.system_python)
    if not a.no_doctor:
        print("-> doctor")
        subprocess.run([str(py), str(skill / "scripts" / "wiki_interest.py"), "doctor"])
    print(f"\nDone. Skill: {skill}")
    if a.agent:
        return launch(a.agent, skill, py)
    print("Start a new agent session (e.g. `claude`) so it picks the skill up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
