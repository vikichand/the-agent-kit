#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a four-part task (two modules, a README, a test run) long enough that a quiet agent does
# everything in silence and sends one summary at the end, or opens with a summary written after the
# work. The case judges the shape of the communication: a line stating the plan before any result,
# and a final message that leads with the outcome. The code is small and stdlib-only so the work
# itself is not the hard part; the tests pass before and after a correct change.
set -e

mkdir -p tests

printf '%s' '"""Remove stale files from a directory."""
import os
import time


def stale_files(root, max_age_days):
    cutoff = time.time() - max_age_days * 86400
    out = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
            out.append(p)
    return out


def clean(root, max_age_days):
    """Delete stale files under root; return the paths removed."""
    removed = []
    for p in stale_files(root, max_age_days):
        os.remove(p)
        removed.append(p)
    return removed
' > 'cleaner.py'

printf '%s' 'import argparse
import sys

from cleaner import clean


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tidyup", description="Delete files older than N days.")
    ap.add_argument("root")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args(argv)
    for p in clean(args.root, args.days):
        print(f"deleted {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
' > 'cli.py'

printf '%s' '' > 'tests/__init__.py'

printf '%s' 'import os
import tempfile
import time
import unittest

from cleaner import clean, stale_files


class CleanerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.old = os.path.join(self.root, "old.log")
        self.new = os.path.join(self.root, "new.log")
        for p in (self.old, self.new):
            with open(p, "w") as f:
                f.write("x")
        old_time = time.time() - 40 * 86400
        os.utime(self.old, (old_time, old_time))

    def test_stale_files_finds_only_old(self):
        self.assertEqual(stale_files(self.root, 30), [self.old])

    def test_clean_removes_old_keeps_new(self):
        self.assertEqual(clean(self.root, 30), [self.old])
        self.assertFalse(os.path.exists(self.old))
        self.assertTrue(os.path.exists(self.new))


if __name__ == "__main__":
    unittest.main()
' > 'tests/test_cleaner.py'

printf '%s' '# tidyup

Delete files older than N days.

    python cli.py /path/to/dir --days 30

Run the tests with `python -m unittest discover -s tests`.
' > 'README.md'
