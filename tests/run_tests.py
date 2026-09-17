#!/usr/bin/env python3
"""Self-contained runner. Walks tests/test_*.py and calls every test_* function.
The files are plain pytest-style functions, so `python3 -m pytest tests/ -q`
works unchanged wherever pytest is installed.

    python3 tests/run_tests.py            # everything
    python3 tests/run_tests.py export     # only tests whose name contains "export"
"""
import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def collect():
    for fn in sorted(os.listdir(HERE)):
        if not (fn.startswith("test_") and fn.endswith(".py")):
            continue
        spec = importlib.util.spec_from_file_location(fn[:-3], os.path.join(HERE, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in sorted(vars(mod)):
            if name.startswith("test_") and callable(getattr(mod, name)):
                yield fn[:-3], name, getattr(mod, name)


def main(argv):
    want = argv[0] if argv else ""
    passed, failed = 0, []
    for modname, name, fn in collect():
        if want and want not in name and want not in modname:
            continue
        try:
            fn()
            passed += 1
            print("  ok   %s.%s" % (modname, name))
        except Exception:
            failed.append((modname, name, traceback.format_exc()))
            print("  FAIL %s.%s" % (modname, name))
    for modname, name, tb in failed:
        print("\n--- %s.%s ---\n%s" % (modname, name, tb))
    print("\n%d passed, %d failed" % (passed, len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
