"""ChangeMesh donor manifest linter wrapper."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    target = (
        Path(__file__).resolve().parent.parent / "tools" / "governance" / "donor_manifest_lint.py"
    )
    res = subprocess.run([sys.executable, str(target)] + sys.argv[1:])
    sys.exit(res.returncode)
