import platform
import sys


def main_cli():
    if sys.version_info < (3, 6):
        # We intentionally don't use any new syntax here
        print("PDPy11 cannot run on such an old Python version as " + platform.python_version() + ". Python 3.6+ is supported.", file=sys.stderr)
        raise SystemExit(1)


    # pylint: disable=redefined-outer-name,import-outside-toplevel
    from ._cli import main_cli
    main_cli()
