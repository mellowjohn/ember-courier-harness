"""Run fixture tests with host Muse discovery disabled, even for imported aliases."""
import argparse
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test*.py')
    args = parser.parse_args(argv)
    # Tests of the provider adapter use explicit synthetic binaries or their own
    # local mocks. An unstubbed app workflow must not discover the user's Muse.
    with patch('ember_harness.muse_chat.installed_binary', return_value=None):
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == '__main__':
    raise SystemExit(main())
