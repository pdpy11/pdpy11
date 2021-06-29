import json
import pytest

from pdp.parser import parse

import util


def expect_parsing_warning(code, *warnings):
    with util.expect_warning(*warnings):
        parse("test.mac", code)

def expect_parsing_error(code, *errors):
    with util.expect_error(*errors):
        parse("test.mac", code)

def expect_no_parsing_warnings(code):
    with util.expect_no_warnings():
        parse("test.mac", code)


def test_unexpected_reserved_name():
    expect_parsing_warning("mov: nop", "suspicious-name")
    expect_parsing_warning("fadd: nop", "suspicious-name")
    expect_parsing_warning("r0: nop", "suspicious-name")

    expect_parsing_warning("mov = 1", "suspicious-name")
    expect_parsing_warning("fadd = 1", "suspicious-name")
    expect_parsing_warning("r0 = 1", "suspicious-name")

    expect_parsing_warning("clr mov:", "suspicious-name")
    expect_parsing_warning("clr fadd:", "suspicious-name")
    expect_parsing_warning("clr r0:", "suspicious-name")

    expect_parsing_warning("mov clr, r1", "suspicious-name")

    expect_parsing_warning("clr mov", "missing-newline")
    expect_parsing_warning("clr fadd", "missing-newline")
    expect_no_parsing_warnings("clr r0")

    expect_parsing_warning("r0", "suspicious-name")


def test_string():
    expect_parsing_error("s = \"\\f\"", "invalid-escape")
    expect_parsing_error("s = '", "unterminated-string")
    expect_parsing_error("s = 'a'", "invalid-character")
    expect_parsing_error("s = ''", "invalid-character")
    expect_parsing_error("s = \"a", "unterminated-string")


def test_insn_syntax():
    expect_parsing_error("insn,", "invalid-insn")
    expect_parsing_error("insn#1", "missing-whitespace")
    expect_parsing_error("insn #(1)nop", "missing-whitespace")
    expect_no_parsing_warnings("insn #(1) nop")
    expect_parsing_warning("insn .word 1", "missing-newline")
    expect_parsing_error("insn%", "missing-newline", "invalid-insn")
