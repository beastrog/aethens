"""``python -m aethens`` is the same as the ``aethens`` console script."""

import sys

from aethens.cli import main

sys.exit(main())
