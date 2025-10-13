"""Module shim for python -m rocforge_ci."""
from __future__ import annotations

import sys

from ci.rocforge_ci.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
