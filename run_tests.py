#!/usr/bin/env python3
"""Run the whole suite in one interpreter. No test framework required.

Every module the tests touch is passed its state, not reaching for a module
global — the conversation state now lives on a Session the tests construct, the
database and config likewise (see docs/adr/0004). So the files can share one
interpreter: nothing one file sets up leaks into the next. Each test file also
still runs standalone (`python tests/test_x.py`) via its own __main__ block.

    python run_tests.py              # everything
    python run_tests.py mail board   # only files whose name contains these
"""

import contextlib
import importlib
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
TESTS = ROOT / "tests"


def main(patterns):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(TESTS))

    files = sorted(TESTS.glob("test_*.py"))
    if patterns:
        files = [f for f in files if any(p in f.name for p in patterns)]
    if not files:
        print("no test files matched")
        return 1

    width = max(len(f.stem) for f in files)
    total = 0
    failed = []

    for path in files:
        module = importlib.import_module(path.stem)
        tests = [v for k, v in sorted(vars(module).items())
                 if k.startswith("test_") and callable(v)]
        file_failures = []
        for test in tests:
            total += 1
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    test()
            except Exception as error:            # noqa: BLE001 - report, don't stop
                file_failures.append((test.__name__, error))

        count = len(tests)
        ok = count - len(file_failures)
        print(f"{path.stem:<{width}}  {ok}/{count} passed")
        for name, error in file_failures:
            print(f"    FAIL {name}: {type(error).__name__}: {error}")
            failed.append(f"{path.stem}::{name}")

    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"{total} tests passed across {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
