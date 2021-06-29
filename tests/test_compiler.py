import pytest
import warnings

from pdp.compiler import Compiler
from pdp.parser import parse

from old_pdpy11.pdpy11.compiler import Compiler as OldCompiler
import util


def compile(source):
    comp = Compiler()
    comp.add_files([parse("test.mac", source)])
    base, binary = comp.link()
    return base, binary


def compile_old(source):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        compiler = OldCompiler(syntax="pdpy11", link=0o1000, file_list=[], project=None)
        compiler.include_root = None
        compiler.compileFile("test.mac", source)
        compiler.link()
    return compiler.link_address, bytes(compiler.output)


def compare_with_old(source):
    assert compile(source) == compile_old(source)


def expect_same(source1, source2):
    assert compile(source1) == compile(source2)


def expect_binary(source, binary):
    assert compile(source)[1] == binary



@pytest.mark.parametrize(
    "code",
    [
        "halt", "wait", "rti", "bpt", "iot", "reset", "rtt", "clc", "clv",
        "clz", "cln", "ccc", "sec", "sev", "sez", "sen", "scc", "nop"
    ]
)
def test_zero_operand(code):
    compare_with_old(code)


@pytest.mark.parametrize("insn", ["clr", "inc", "tstb"])
@pytest.mark.parametrize(
    "operand",
    [
        "r0", "r1", "r6", "sp", "pc", "#123", "10", "-57", "@#123", "@12",
        "(r3)", "(r5)+", "-(r2)", "@1(sp)", "@(r1)+", "@-(r2)"
    ]
)
def test_single_operand(insn, operand):
    compare_with_old(f"{insn} {operand}")


@pytest.mark.parametrize("insn", ["mov", "add", "cmpb"])
@pytest.mark.parametrize(
    "op1",
    [
        "r0", "r1", "r6", "sp", "pc", "#123", "10", "-57", "@#123", "@12",
        "(r3)", "(r5)+", "-(r2)", "5(r2)", "@1(sp)", "@(r1)+", "@-(r2)"
    ]
)
@pytest.mark.parametrize("op2", ["r1", "@#120"])
def test_two_operands(insn, op1, op2):
    compare_with_old(f"{insn} {op1}, {op2}")
    compare_with_old(f"{insn} {op2}, {op1}")


def test_str_as_int():
    expect_same("tst #'a", "tst #97.")


def test_metacommands():
    expect_binary(".byte 0x12", b"\x12")
    expect_binary(".byte 0x12, 0x34", b"\x12\x34")
    with util.expect_warning("use-ascii"):
        expect_binary(".byte 'x", b"x")

    expect_binary(".word 0x1234", b"\x34\x12")
    expect_binary(".word 0x1234, 0x5678", b"\x34\x12\x78\x56")
    with util.expect_warning("use-ascii"):
        expect_binary(".word \"ab\"", b"ab")

    with util.expect_warning("use-ascii", "empty-pack"):
        expect_binary(".word \"\"", b"\x00\x00")

    expect_binary(".dword 0x12345678", b"\x34\x12\x78\x56")
    expect_binary(".dword 0x12345678, 0x90abcdef", b"\x34\x12\x78\x56\xab\x90\xef\xcd")
    with util.expect_warning("use-ascii"):
        expect_binary(".dword \"abcd\"", b"abcd")

    expect_binary(".ascii \"Hello, world!\"", b"Hello, world!")
    expect_binary(".asciz \"Hello, world!\"", b"Hello, world!\x00")
    expect_binary(".blkb 10", b"\x00" * 8)
    expect_binary(".blkw 10", b"\x00" * 16)

    expect_binary(".byte 1\n.even", b"\x01\x00")
    expect_binary(".byte 1, 2\n.even", b"\x01\x02")

    expect_same(".repeat 10 { tst #1 }", "tst #1\n" * 8)
    expect_binary(".repeat 10 { .blkb cnt }\ncnt = 10", b"\x00" * 64)

    with util.expect_error("excess-hash"):
        expect_binary(".byte #0x12", b"\x12")

    with util.expect_warning("meta-typo"):
        expect_binary("blkb 10", b"\x00" * 8)


def test_math():
    expect_same(".word 1 + 2", ".word 3")
    expect_same(".word 2 * 3", ".word 6")
    expect_same(".word 1 - 2", ".word -1")
    expect_same(".word 5 / 2", ".word 2")
    expect_same(".word 6 / 2", ".word 3")
    expect_same(".word -5 / 2", ".word -3")
    expect_same(".word -6 / 2", ".word -3")
    expect_same(".word 1 + 2 * 3", ".word 7")
    expect_same(".word 1 * 2 + 3", ".word 5")
    expect_same(".word (1 + 2) * 3", ".word 11")
    expect_same(".word 5 * (2 + 3)", ".word 31")
    expect_same(".word +6", ".word 6")
    expect_same(".word +(6)", ".word 6")
    expect_same(".word -(6)", ".word -6")


def test_end():
    expect_same("nop\n.end\nccc", "nop")

    with util.expect_warning("meta-typo"):
        expect_same("nop\nend\nccc", "nop")


# def test_typing():
#     with util.expect_error("meta-type-mismatch"):
#         compile("lbl = 1\nlbl")
#     with util.expect_error("meta-type-mismatch"):
#         compile("lbl:\nlbl")
#     with util.expect_error("meta-type-mismatch"):
#         compile("lbl\nlbl = 1")
#     with util.expect_error("meta-type-mismatch"):
#         compile("lbl\nlbl:")


def test_deferred():
    expect_same("x = 1\ntst #x", "tst #1")
    expect_same("tst #x\nx = 1", "tst #1")

    expect_same("lbl: tst lbl", "tst .")
    expect_same("tst lbl\nlbl:", "tst .+4")

    expect_same("x = 1\n.word x", ".word 1")
    expect_same(".word x\nx = 1", ".word 1")


def test_addressing():
    compare_with_old("jsr sp, 57")

    with util.expect_error("invalid-addressing"):
        compile("jsr 123, 57")

    with util.expect_error("invalid-addressing"):
        compile("sob 123, 57")

    with util.expect_warning("implicit-index"):
        expect_same("inc @(r2)", "inc @0(r2)")


@pytest.mark.parametrize("insn", ["br", "bge"])
def test_branching(insn):
    compare_with_old(f"{insn} . + 4")
    compare_with_old(f"{insn} 1\n1:")
    expect_same(f"{insn} 1\n1:", f"{insn} lbl\nlbl:")
    expect_same(f"{insn} lbl + 2\nlbl: .word 0", f"{insn} lbl\n.word 0\nlbl:")
