import json
import pytest

from pdp.operators import *
from pdp.parser import parse
from pdp import reports


def expect_warning(code, *warnings):
    matched_warnings = []

    def report_handler(priority, identifier, *lst_reports):
        if priority != reports.warning:
            raise Exception(identifier)
        matched_warnings.append(identifier)

    with reports.handle_reports(report_handler):
        parse("test.mac", code)

    assert sorted(matched_warnings) == sorted(warnings)


def expect_error(code, *errors):
    matched_errors = []
    is_error_condition = False

    def report_handler(priority, identifier, *lst_reports):
        nonlocal is_error_condition
        if priority is not reports.warning:
            is_error_condition = True
        matched_errors.append(identifier)

    try:
        with reports.handle_reports(report_handler):
            parse("test.mac", code)
    except reports.UnrecoverableError:
        pass
    else:
        assert False, "Should raise an error (critical or not)"

    assert sorted(matched_errors) == sorted(errors)
    assert is_error_condition


def expect_no_warnings(code):
    expect_warning(code)  # I know, semantics kinda suck


def test_unexpected_reserved_name():
    expect_warning("mov: nop", "suspicious-name")
    expect_warning("fadd: nop", "suspicious-name")
    expect_warning("r0: nop", "suspicious-name")

    expect_warning("mov = 1", "suspicious-name")
    expect_warning("fadd = 1", "suspicious-name")
    expect_warning("r0 = 1", "suspicious-name")

    expect_warning("clr mov:", "suspicious-name")
    expect_warning("clr fadd:", "suspicious-name")
    expect_warning("clr r0:", "suspicious-name")

    expect_warning("clr mov", "missing-newline")
    expect_warning("clr fadd", "missing-newline")
    expect_no_warnings("clr r0")

    expect_warning("r0", "suspicious-name")


def test_string():
    expect_error("s = \"\\f\"", "invalid-escape")
    expect_error("s = '", "invalid-character")
    expect_error("s = 'a'", "invalid-character")
    expect_error("s = \"a", "invalid-string")


def test_insn_syntax():
    expect_error("insn,", "invalid-insn")
    expect_error("insn#1", "missing-whitespace")
    expect_error("insn #(1)nop", "missing-whitespace")
    expect_no_warnings("insn #(1) nop")
    expect_warning("insn .word 1", "missing-newline")
    expect_error("insn%", "missing-newline", "missing-whitespace", "invalid-insn")
