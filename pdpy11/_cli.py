import argparse
import codecs
import os
import platform
import sys
import traceback

# Importing bk_encoding is not pure
from . import bk_encoding  # pylint: disable=unused-import

from .compiler import Compiler
from .devices import open_device
from .formats import file_formats
from . import parser
from . import reports
from .version import __version__ as version


argparser = argparse.ArgumentParser(prog="pdpy11", description="Cross-assembler for PDP-11", epilog="""PDPy11 is licensed under GNU GPLv3 or (at your option) any later version.""")

argparser.add_argument("infiles", metavar="infile", type=str, nargs="+", help="assembly source files")

argparser.add_argument("-o", metavar="outfile", dest="outfile", type=str, help="name of output file")

argparser.add_argument("--implicit-bin", action="store_true", help="if no output file is configured in both source and CLI arguments, assume an implicit make_bin directive")
argparser.add_argument("--lst", action="store_true", help="generate a listing file")

argparser.add_argument("--charset", metavar="encoding", type=str, default="bk", help="output string encoding for .ascii and other directives (default: bk)")
argparser.add_argument("--report-format", choices=["graphical", "bare"], default="graphical", help="format in which error messages and warnings are printed")

argparser.add_argument("--version", "-v", action="version", version=f"%(prog)s {version} running on {platform.python_implementation()} {platform.python_version()}")


def main_cli():
    args = argparser.parse_args()


    try:
        codecs.lookup(args.charset)
    except LookupError:
        print(f"'{args.charset}' encoding is unsupported", file=sys.stderr)
        sys.exit(1)


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
        sys.exit(1)

    report_handler = {
        "graphical": reports.GraphicalHandler,
        "bare": reports.BareHandler
    }[args.report_format]()

    try:
        with reports.handle_reports(report_handler):
            parsed_files = []
            for path, source in files_to_parse:
                parsed_files.append(parser.parse(path, source))

            comp = Compiler(output_charset=args.charset)
            base, code = comp.compile_and_link_files(parsed_files)


        with reports.handle_reports(report_handler):
            was_emitted, emitted_file = comp.emit_files(base, code)


        if args.outfile is None and not was_emitted:
            if args.implicit_bin:
                filename = files_to_parse[0][0]
                if filename.lower().endswith(".mac"):
                    filename = filename[:-4]
                args.outfile = filename + ".bin"
            else:
                print("The file was compiled successfully, but no output files were saved because 'make_xxx' directive was not encountered and '-o' option was not passed.", file=sys.stderr)


        if args.outfile is not None:
            output_file = args.outfile

            output_filename = output_file.split("/")[-1]
            output_ext = output_filename.split(".")[-1] if "." in output_filename else ""
            if output_filename.lower().endswith(".bin"):
                output_format = "bin"
            else:
                output_format = "raw"

            emitted_file = {
                "format": output_format,
                "path": output_file
            }

            if output_file in ("-", "-." + output_ext):
                sys.stdout.buffer.write(file_formats[output_format](base, code))
            else:
                try:
                    with open_device(output_file, "wb") as f:
                        f.write(file_formats[output_format](base, code))
                except IOError as ex:
                    print(f"Could not write to '{output_file}':\n{ex}", file=sys.stderr)
                    sys.exit(1)
                else:
                    print(f"File '{output_file}' was written in format '{output_format}'", file=sys.stderr)


        if args.lst is not False:
            if emitted_file is None:
                print(f"No listing file was generated because no output file was specified", file=sys.stderr)
            else:
                lst_file = emitted_file["path"]
                if lst_file.endswith("." + emitted_file["format"]):
                    lst_file = lst_file.rpartition(".")[0]
                lst_file += ".lst"
                if lst_file == "-.lst":
                    lst_file = "listing.lst"

                try:
                    with open_device(lst_file, "w") as f:
                        f.write(comp.generate_listing())
                except IOError as ex:
                    print(f"Could not write to '{lst_file}':\n{ex}", file=sys.stderr)
                    sys.exit(1)
                else:
                    print(f"File '{lst_file}' was written in format 'lst'", file=sys.stderr)
    except reports.UnrecoverableError:
        sys.exit(1)
    except Exception as ex:  # pylint: disable=broad-except
        print("An unexpected internal compiler error happened.\nPlease report this to https://github.com/pdpy11/pdpy11/issues.\nThe following information will be of interest to the maintainer\n(hopefully along with some samples for reproduction):\n\n---\n", file=sys.stderr)
        print(f"Version: pdpy11 {version}\nPython: {platform.python_implementation()} {platform.python_version()}\nPlatform: {platform.platform()}\n", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
