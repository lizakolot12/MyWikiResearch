"""Import shim: exposes scripts/wiki_interest.py:main to tests."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parent.parent / "scripts" / "wiki_interest.py"
_spec = importlib.util.spec_from_file_location("wiki_interest_script", _p)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main
