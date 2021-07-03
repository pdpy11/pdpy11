import argparse
import os
import platform
import sys
import traceback

from .compiler import Compiler
from .formats import file_formats
from . import parser
from . import reports
from .version import __version__ as version


argparser = argparse.ArgumentParser(prog="pdpy11", description="Cross-assembler for PDP-11", epilog="""PDPy11 is licensed under GNU GPLv3 or (at your option) any later version.""")

argparser.add_argument("infiles", metavar="infile", type=str, nargs="+", help="assembly source files")

argparser.add_argument("-o", metavar="outfile", dest="outfile", type=str, help="name of output file")

# argparser.add_argument("--charset", metavar="coding", type=str, nargs=1, help="output string encoding for .ascii and other directives")
argparser.add_argument("--report-format", choices=["graphical", "bare"], default="graphical", help="format in which error messages and warnings are printed")

argparser.add_argument("--version", "-v", action="version", version=f"%(prog)s {version} running on {platform.python_implementation()} {platform.python_version()}")


def main_cli():
    args = argparser.parse_args()

    error = False
    files_to_parse = []
    for path in args.infiles:
        try:
            if path == "-":
                path = "stdin"
                source = sys.stdin.read()
            else:
                path = os.path.abspath(path)
                with open(path, encoding="utf-8") as f:
                    source = f.read()
            files_to_parse.append((path, source))
        except IOError as ex:
            print(f"Could not read source file '{path}':\n{ex}", file=sys.stderr)
            error = True
        except UnicodeDecodeError as ex:
            print(f"Source file '{path}' is not in UTF-8:\n{ex}", file=sys.stderr)
            error = True

    if error:
        raise SystemExit(1)

    report_handler = {
        "graphical": reports.GraphicalHandler,
        "bare": reports.BareHandler
    }[args.report_format]()

    try:
        with reports.handle_reports(report_handler):
            parsed_files = []
            for path, source in files_to_parse:
                parsed_files.append(parser.parse(path, source))

            comp = Compiler()
            comp.add_files(parsed_files)

            base, code = comp.link()


        with reports.handle_reports(report_handler):
            was_emitted = comp.emit_files()


        if args.outfile is not None:
            output_file = args.outfile

            output_filename = output_file.split("/")[-1]
            output_ext = output_filename.split(".")[-1] if "." in output_filename else None
            if output_ext.lower() in ("bin", "wav"):
                output_format = output_ext.lower()
            else:
                output_format = "raw"

            try:
                with open(output_filename, "wb") as f:
                    f.write(file_formats[output_format](base, code))
            except IOError as ex:
                print(f"Could not write to output file '{output_file}':\n{ex}", file=sys.stderr)
                raise SystemExit(1)
            else:
                print(f"File {output_filename} was saved in format '{output_format}'", file=sys.stderr)

        if args.outfile is None and not was_emitted:
            print("The file was compiled successfully, but no output files were saved because 'make_xxx' directive was not encountered and '-o' option was not passed.", file=sys.stderr)
    except reports.UnrecoverableError:
        raise SystemExit(1)
    except Exception as ex:
        print("An unexpected internal compiler error happened.\nPlease report this to https://github.com/pdpy11/pdpy11/issues.\nThe following information will be of interest to the maintainer\n(hopefully along with some samples for reproduction):\n\n---\n", file=sys.stderr)
        print(f"Version: pdpy11 {version}\nPython: {platform.python_implementation()} {platform.python_version()}\nPlatform: {platform.platform()}\n", file=sys.stderr)
        traceback.print_exc()
