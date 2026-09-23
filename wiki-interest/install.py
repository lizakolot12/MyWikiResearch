#!/usr/bin/env python3
"""Install the wiki-interest skill in one command (stdlib only, Python 3.10+).

  python install.py                     copy to ~/.claude/skills/wiki-interest + .venv + deps + doctor
  python install.py --project DIR       copy to DIR/.claude/skills/wiki-interest (skill for one project)
  python install.py --dest DIR          copy to any skills folder (other agents), DIR/wiki-interest
  python install.py --link              symlink instead of copy: edits in this repo apply at once
  python install.py --deps-only         only create .venv here and install dependencies
  python install.py --zip FILE.zip      build an archive to upload to claude.ai (Settings > Skills)

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
    if dest.is_symlink() or (link and dest.exists()):
        # an old link, or a copy that becomes a link: the cache stays in the source folder
        dest.unlink() if dest.is_symlink() else shutil.rmtree(dest)
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


def build_zip(out: Path) -> None:
    out = out.resolve()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.rglob("*")):
            rel = f.relative_to(SRC)
            if f.is_file() and not any(fnmatch(part, pat) for part in rel.parts for pat in SKIP):
                z.write(f, Path(NAME) / rel)
    print(f"-> {out}  (upload it in claude.ai: Settings > Capabilities > Skills)")


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
    a = p.parse_args(argv)

    if a.zip:
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
    print(f"\nDone. Skill: {skill}\nRestart the agent session so it picks the skill up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
