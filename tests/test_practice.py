import os
import pytest
import re
import warnings

from pdpy11 import bk_encoding
from pdpy11 import reports
from pdpy11.compiler import Compiler
from pdpy11.formats import file_formats
from pdpy11.parser import parse

from .old_pdpy11.pdpy11.compiler import Compiler as OldCompiler
from .resources import resources
from . import util


DATA_ROOT = os.path.join(os.path.dirname(__file__), "practice")


@pytest.mark.parametrize("test_name", os.listdir(DATA_ROOT))
def test_from_file(test_name):
    source_path = os.path.join(DATA_ROOT, test_name, "code.mac")
    with open(source_path) as f:
        source = f.read()

    comp = Compiler()

    def report_handler(priority, identifier, *lst_reports):
        if priority != reports.warning:
            raise Exception((identifier, lst_reports))  # pragma: no cover

    with reports.handle_reports(report_handler):
        parsed_file = parse(source_path, source)
        base, code = comp.compile_and_link_files([parsed_file])

    result = file_formats["bin"](base, code)

    output_path = os.path.join(DATA_ROOT, test_name, "out.bin")
    with open(output_path, "rb") as f:
        assert result == f.read()
