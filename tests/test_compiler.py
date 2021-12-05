import pytest
import re
import warnings

from pdpy11 import bk_encoding
from pdpy11.compiler import Compiler
from pdpy11.parser import parse

from .old_pdpy11.pdpy11.compiler import Compiler as OldCompiler
from .resources import resources
from . import util


def compile(source, **kwargs):
    comp = Compiler(**kwargs)
    base, binary = comp.compile_and_link_files([parse("test.mac", source)])
    return base, binary


def compile_and_emit(file_path, source):
    comp = Compiler()
    base, binary = comp.compile_and_link_files([parse(file_path, source)])
    return comp.emit_files(base, binary)


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


def expect_same(source1, source2, **kwargs):
    assert compile(source1, **kwargs) == compile(source2, **kwargs)


def expect_binary(source, binary, **kwargs):
    assert compile(source, **kwargs)[1] == binary



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
        "(r0)", "(r0)+", "-(r0)", "@1(r0)", "@(r0)+", "@-(r0)"
    ]
)
def test_single_operand(insn, operand):
    compare_with_old(f"{insn} {operand}")


@pytest.mark.parametrize("insn", ["mov", "add", "cmp", "cmpb"])
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


def test_immediate_operand():
    compare_with_old("emt 123")
    compare_with_old("emt 0")
    expect_same("emt -1", "emt 377")

    with util.expect_warning("excess-hash"):
        expect_same("emt #15", "emt 15")

    with util.expect_error("value-out-of-bounds"):
        expect_same("emt 400", "emt 0")
    with util.expect_error("value-out-of-bounds"):
        expect_same("emt 401", "emt 0")
    with util.expect_error("value-out-of-bounds"):
        expect_same("emt -400", "emt 0")
    with util.expect_error("value-out-of-bounds"):
        expect_same("emt -401", "emt 0")

    compare_with_old("mark 0")
    compare_with_old("mark 77")
    with util.expect_error("value-out-of-bounds"):
        expect_same("mark 100", "mark 0")
    with util.expect_error("value-out-of-bounds"):
        expect_same("mark -1", "mark 0")


def test_str_as_int():
    expect_same("tst #'a", "tst #97.")


def test_metacommands():
    expect_binary(".byte 0x12", b"\x12")
    expect_binary(".byte 0x12, 0x34", b"\x12\x34")

    expect_binary(".word 0x12", b"\x12\x00")
    expect_binary(".word 0x1234", b"\x34\x12")
    expect_binary(".word 0x1234, 0x5678", b"\x34\x12\x78\x56")

    expect_binary(".dword 0x78", b"\x00\x00\x78\x00")
    expect_binary(".dword 0x5678", b"\x00\x00\x78\x56")
    expect_binary(".dword 0x345678", b"\x34\x00\x78\x56")
    expect_binary(".dword 0x12345678", b"\x34\x12\x78\x56")
    expect_binary(".dword 0x12345678, 0x90abcdef", b"\x34\x12\x78\x56\xab\x90\xef\xcd")

    expect_binary(".ascii \"Hello, world!\"", b"Hello, world!")
    expect_binary(".asciz \"Hello, world!\"", b"Hello, world!\x00")
    expect_binary(".ascii \"Hello\"<12>\"world!\"", b"Hello\nworld!")
    expect_binary(".ascii <12>", b"\n")
    expect_binary(".blkb 10", b"\x00" * 8)
    expect_binary(".blkw 10", b"\x00" * 16)

    expect_binary(".byte 1\n.even", b"\x01\x00")
    expect_binary(".byte 1, 2\n.even", b"\x01\x02")
    expect_binary(".byte 1\n.odd", b"\x01")
    expect_binary(".byte 1, 2\n.odd", b"\x01\x02\x00")

    expect_same(".repeat 10 { tst #1 }", "tst #1\n" * 8)
    expect_binary(".repeat 10 { .blkb cnt }\ncnt = 10", b"\x00" * 64)

    with util.expect_error("odd-address"):
        expect_same(".byte 1\n.word 2", ".byte 1, 0\n.word 2")
    with util.expect_error("odd-address"):
        expect_same(".byte 1\n.dword 2", ".byte 1, 0\n.dword 2")

    with util.expect_warning("implicit-operand"):
        expect_same(".byte", ".byte 0")
    with util.expect_warning("implicit-operand"):
        expect_same(".word", ".word 0")
    with util.expect_warning("implicit-operand"):
        expect_same(".dword", ".dword 0")

    with util.expect_error("excess-hash"):
        expect_binary(".byte #0x12", b"\x12")

    with util.expect_warning("meta-typo"):
        expect_binary("blkb 10", b"\x00" * 8)

    with util.expect_error("wrong-meta-operands"):
        compile(".repeat 1")
    with util.expect_error("wrong-meta-operands"):
        compile(".blkb")
    with util.expect_error("wrong-meta-operands"):
        compile(".blkb 1, 2")


def test_implicit_casts():
    # with util.expect_warning("use-ascii"):
    #     expect_binary(".byte 'x", b"x")
    # with util.expect_warning("use-ascii", "empty-pack"):
    #     expect_binary(".byte \"\"", b"\x00")

    # with util.expect_warning("use-ascii"):
    #     expect_binary(".word 'x", b"x\x00")
    # with util.expect_warning("use-ascii"):
    #     expect_binary(".word \"ab\"", b"ab")

    # with util.expect_warning("use-ascii", "empty-pack"):
    #     expect_binary(".word \"\"", b"\x00\x00")

    # with util.expect_warning("use-ascii"):
    #     expect_binary(".dword \"abcd\"", b"abcd")
    # with util.expect_warning("use-ascii"):
    #     expect_binary(".dword \"abc\"", b"abc\x00")
    # with util.expect_warning("use-ascii"):
    #     expect_binary(".dword \"ab\"", b"ab\x00\x00")
    # with util.expect_warning("use-ascii"):
    #     expect_binary(".dword \"a\"", b"a\x00\x00\x00")

    # with util.expect_warning("implicit-pack"):
    #     code = compile("mov #\"a\", r0")
    # assert code == compile("mov #'a, r0")

    # with util.expect_warning("implicit-pack"):
    #     code = compile("mov #s, r0\ns = \"ab\"")
    # assert code == compile("mov #0x6261, r0")

    # with util.expect_error("too-long-string", "use-ascii"):
    #     expect_same(".byte \"ab\"", ".ascii \"a\"")
    # with util.expect_error("too-long-string", "use-ascii"):
    #     expect_same(".word \"abc\"", ".ascii \"ab\"")
    # with util.expect_error("too-long-string", "use-ascii"):
    #     expect_same(".dword \"abcde\"", ".ascii \"abcd\"")

    expect_binary(".byte 'x", b"x")
    expect_binary(".word 'x", b"x\x00")
    expect_binary(".word \"ab", b"ab")

    with util.expect_warning("excess-quote"):
        expect_binary(".byte ''", b"\x00")
    with util.expect_warning("excess-quote"):
        expect_binary(".byte 'x'", b"x")
    with util.expect_warning("excess-quote"):
        expect_binary(".word 'x'", b"x\x00")
    with util.expect_warning("excess-quote"):
        expect_binary(".word \"ab\"", b"ab")
    with util.expect_warning("excess-quote"):
        expect_binary(".word \"x\"", b"x\x00")
    with util.expect_warning("excess-quote"):
        expect_binary(".word \"\"", b"\x00\x00")

    expect_binary(".dword \"ab", b"\x00\x00ab")
    expect_binary(".dword 'a", b"\x00\x00a\x00")

    with util.expect_error("value-out-of-bounds"):
        expect_same(".byte \"ab", ".ascii \"a\"")



def test_out_of_bounds():
    with util.expect_error("value-out-of-bounds"):
        compile(".repeat -1 { }")

    expect_same(".blkb 0", "")
    with util.expect_error("value-out-of-bounds"):
        compile(".blkb -1")

    compile(".word 0")
    compile(".word 177777")
    compile(".word -177777")
    with util.expect_error("value-out-of-bounds"):
        compile(".word 200000")
    with util.expect_error("value-out-of-bounds"):
        compile(".word -200000")


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
    expect_same(".word +<6>", ".word 6")
    expect_same(".word -<6>", ".word -6")
    expect_same(".word ~100", ".word 177677")
    expect_same(".word ^C100", ".word 177677")
    expect_same(".word ^C(20+60)", ".word 177677")
    expect_same(".word ^C1+2", ".word 0")  # as documented in Macro-11 docs
    expect_same(".word 179. % 57", ".word 46")
    expect_same(".word 0b1100 & 0b1010", ".word 0b1000")
    expect_same(".word 0b1100 ^ 0b1010", ".word 0b0110")
    expect_same(".word 0b1100 | 0b1010", ".word 0b1110")
    expect_same(".word 0b1100 ! 0b1010", ".word 0b1110")
    expect_same(".word 123 << 6", ".word 12300")
    expect_same(".word 1337 >> 6", ".word 13")
    expect_same(".word 123 _ 6", ".word 12300")
    expect_same(".word 1337 _ -6", ".word 13")

    with util.expect_error("arithmetic-error"):
        expect_same(".word 5 / 0", ".word 0")
    with util.expect_error("arithmetic-error"):
        expect_same(".word 5 % 0", ".word 0")


def test_variables():
    expect_same("a = 5\n.word a", ".word 5")
    expect_same(".word a\na = 5", ".word 5")
    expect_same(".word a\na = b\nb = c\nc = 5", ".word 5")

@pytest.mark.parametrize("op", ["+", "-", "*", "/", "%", "<<", ">>", "_"])
def test_variables_infix(op):
    expect_same(f".word a {op} b\na = 5\nb = 3", f".word 5 {op} 3")
    expect_same(f".word (. {op} .) & 177777", f".word (1000 {op} 1000) & 177777")

@pytest.mark.parametrize("op", ["+", "-", "~", "^C", "^c"])
def test_variables_prefix(op):
    expect_same(f".word {op} a\na = 5", f".word {op} 5")
    expect_same(f".word {op} .", f".word {op} 1000")


def test_linear_polynomial():
    expect_same(".link 1000 + a - b\na: .word 123\nb:", ".link 776\n.word 123")
    expect_same(".link 1000 + (a >> 0) - (b << 1) + (b >> 0)\na: .word 123\nb:", ".link 776\n.word 123")
    expect_same(".link 1000 + x - x\nx: .word 123", ".link 1000\n.word 123")
    expect_same(".link 1000 + y - y\ny = .", ".link 1000")
    expect_same(".link 1000 + z - z\nz = . >> 1", ".link 1000")
    expect_same(".link 1000 + a - a\na = b >> 1\nb = .", ".link 1000")
    expect_same(".dword (. + 2) * .", ".dword (1000 + 2) * 1000")
    expect_same(".word (a - .) * .\na = .", ".word 2000")
    expect_same(".word (a - .) * .\na:", ".word 2000")
    expect_same(".word 2 * .", ".word 2000")
    expect_same(".word 2 * (3 * . + 4)", ".word 6010")


def test_symbol_propagation():
    expect_same("d = c*2\ne = d*2 + 1\n.link e*3 + 1 - . * 14\n.word .\nc:", ".link 34\n.word .")


def test_unexpected_register():
    with util.expect_error("unexpected-register"):
        compile("clr r1+1")
    with util.expect_error("unexpected-register"):
        compile("clr (r1+1)")
    with util.expect_error("unexpected-register"):
        compile("clr <r1>")


def test_end():
    expect_same("nop\n.end\nccc", "nop")

    with util.expect_warning("meta-typo"):
        expect_same("nop\nend\nccc", "nop")


def test_typing():
    with util.expect_error("meta-type-mismatch"):
        compile("lbl = 1\nlbl")
    with util.expect_error("meta-type-mismatch"):
        compile("lbl:\nlbl")

    # Not working yet
    # with util.expect_error("meta-type-mismatch"):
    #     compile("lbl\nlbl = 1")
    # with util.expect_error("meta-type-mismatch"):
    #     compile("lbl\nlbl:")


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

    with util.expect_warning("legacy-deferred"):
        expect_same("clr @r0", "clr (r0)")

    # old pdpy would raise an error here because 57 is not a register
    expect_same("clr -(57)", "clr -57")

    expect_same("clr (-57)", "clr -57")
    expect_same("clr <-57>", "clr -57")


def test_branch():
    compare_with_old("br . + 4")
    compare_with_old("br 1\n1:")
    compare_with_old("bge . + 4")
    compare_with_old("bge 1\n1:")

    expect_same("br 1\n1:", "br lbl\nlbl:")
    expect_same("br lbl + 2\nlbl: .word 0", "br lbl\n.word 0\nlbl:")

    with util.expect_warning("label-fixup"):
        expect_same("br 1 + 2\n1:", "br lbl + 2\nlbl:")
    with util.expect_warning("label-fixup"):
        expect_same("br 2 + 2\n2:", "br lbl + 2\nlbl:")
    with util.expect_warning("label-fixup"):
        expect_same("br 4 + 2\n4:", "br lbl + 2\nlbl:")
    with util.expect_warning("label-fixup"):
        expect_same("br 2 + 4\n2:", "br lbl + 4\nlbl:")

    with util.expect_warning("label-fixup"):
        expect_same("br +1 + 2\n1:", "br lbl + 2\nlbl:")

    expect_same("br 1: + 2\n1:", "br lbl + 2\nlbl:")
    expect_same("br 2 + 1:\n1:", "br lbl + 2\nlbl:")

    compile("br .")
    with util.expect_error("odd-branch"):
        compile("br . + 1")
    with util.expect_error("branch-out-of-bounds"):
        compile("br . + 10000")
    with util.expect_error("branch-out-of-bounds"):
        compile("br . - 10000")

    compare_with_old("sob r0, .")
    compare_with_old("sob r0, . + 2")
    with util.expect_error("odd-branch"):
        compile("sob r0, . - 1")
    with util.expect_error("branch-out-of-bounds"):
        compile("sob r0, . + 4")
    with util.expect_error("branch-out-of-bounds"):
        compile("sob r0, a\nnop\na:")
    with util.expect_error("branch-out-of-bounds"):
        compile("sob r0, . - 1000000")


def test_unexpected_symbol():
    with util.expect_error("unexpected-symbol-definition"):
        compile(".repeat 10 { lbl = 1 }")
    with util.expect_error("unexpected-symbol-definition"):
        compile(".repeat 10 { lbl: }")


def test_duplicate_symbol():
    with util.expect_error("duplicate-symbol"):
        compile("a = 1\na = 2")
    with util.expect_error("duplicate-symbol"):
        compile("a = 1\na = 1")
    with util.expect_error("duplicate-symbol"):
        compile("a:\na:")
    with util.expect_error("duplicate-symbol"):
        compile("a:\na = 1")
    with util.expect_error("duplicate-symbol"):
        compile("a = 1\na:")
    with util.expect_error("duplicate-symbol"):
        compile("1:\n1:")


def test_undefined_symbol():
    with util.expect_error("undefined-symbol"):
        compile("clr @#a")
    with util.expect_error("undefined-symbol", "undefined-symbol"):
        compile("clr a + b")
    with util.expect_error("undefined-symbol", "undefined-symbol", "undefined-symbol"):
        compile("clr a + b\nclr c")


def test_invalid_insn():
    with util.expect_error("unknown-insn"):
        compile("insn")

    with util.expect_error("wrong-operands"):
        compile("clr")
    with util.expect_error("wrong-operands"):
        compile("mov r1")
    with util.expect_error("wrong-operands"):
        compile("mov r1, r2, r3")
    with util.expect_error("wrong-operands"):
        compile("inc r1, r2")
    with util.expect_error("wrong-operands"):
        compile("nop r1")


def test_numbers():
    expect_same(".word 123.", ".word 173")
    expect_same(".word 0x123", ".word 443")
    expect_same(".word 0o123", ".word 123")
    expect_same(".word 0b11010", ".word 32")

    with util.expect_error("invalid-number"):
        expect_same(".word 18", ".word 18.")
    with util.expect_error("invalid-number"):
        expect_same(".word 19", ".word 19.")


def test_error():
    with util.expect_error("user-error"):
        compile(".error")
    with util.expect_error("user-error"):
        compile(".error Hello, world!")

    with util.expect_error("user-error"):
        expect_same(".error\nmov r1, r2", "mov r1, r2")
    with util.expect_error("user-error"):
        expect_same(".error Hello, world!\nmov r1, r2", "mov r1, r2")


def test_radix50():
    expect_same(".rad50 /ABC/", ".word 3223")
    expect_same(".rad50 /AB /", ".rad50 /AB/")
    expect_same(".rad50 //", "")
    expect_same(".rad50 /ABCDEF/", ".rad50 /ABC/\n.rad50 /DEF/")
    expect_same(".rad50 /AB/<35>", ".word 3255")
    expect_same(".rad50 /abc/", ".rad50 /ABC/")

    expect_same(".rad50 /AB/<0>", ".rad50 /AB /")
    expect_same(".rad50 /AB/<47>", ".rad50 /AB9/")
    with util.expect_error("value-out-of-bounds"):
        expect_same(".rad50 /AB/<-1>", ".rad50 /AB /")
    with util.expect_error("value-out-of-bounds"):
        expect_same(".rad50 /AB/<50>", ".rad50 /AB /")

    with util.expect_error("invalid-character"):
        expect_same(".rad50 /AB#/", ".rad50 /AB /")

    expect_same(".word ^RABC", ".rad50 /ABC/")
    expect_same(".word ^RAB", ".rad50 /AB/")
    with util.expect_error("invalid-string"):
        expect_same(".word ^RABCDEF", ".word ^RABC")
    with util.expect_error("invalid-string"):
        expect_same(".word ^R nop", ".word 0\nnop")
    with util.expect_error("invalid-string"):
        expect_same(".word ^R", ".word 0")


def test_insert_file(fs):
    fs.create_file("test_file", contents=b"Hello, world!")
    fs.create_file("unreadable_file", st_mode=0)
    fs.create_dir("test_dir")

    expect_binary("insert_file /test_file/", b"Hello, world!")

    with util.expect_error("io-error"):
        compile("insert_file /non_existant_file/")
    with util.expect_error("io-error"):
        compile("insert_file /test_dir/")
    with util.expect_error("io-error"):
        compile("insert_file /unreadable_file/")


@pytest.mark.parametrize(
    "suffix,input_file_name,output_file_name,file_format,code_prefix",
    [
        ("make_bin", "test.mac", "test.bin", "bin", b"\x00\x02\x02\x00"),
        ("make_bin 'test2.bin'", "test.mac", "test2.bin", "bin", b"\x00\x02\x02\x00"),
        ("make_bin", "dir/test.mac", "dir/test.bin", "bin", b"\x00\x02\x02\x00"),

        ("make_raw", "test.mac", "test", "raw", b""),
        ("make_raw 'test2.raw'", "test.mac", "test2.raw", "raw", b""),
        ("make_raw", "dir/test.mac", "dir/test", "raw", b""),

        # Must not guess file type from extension
        ("make_bin 'test2.raw'", "test.mac", "test2.raw", "bin", b"\x00\x02\x02\x00"),
        ("make_raw 'test2.bin'", "test.mac", "test2.bin", "raw", b""),

        # Source file without .mac extension
        ("make_bin", "test", "test.bin", "bin", b"\x00\x02\x02\x00")
    ]
)
def test_binaries(fs, suffix, input_file_name, output_file_name, file_format, code_prefix):
    fs.create_file(output_file_name)
    assert compile_and_emit(input_file_name, "mov r1, r2\n" + suffix) == (True, {"format": file_format, "path": output_file_name})
    with open(output_file_name, "rb") as f:
        assert f.read() == code_prefix + b"B\x10"


def test_emit(fs):
    assert compile_and_emit("test.mac", "mov r1, r2") == (False, None)

    fs.create_file("test.bin", st_mode=0)
    with util.expect_error("io-error"):
        compile_and_emit("test.mac", "make_bin")


@pytest.mark.parametrize(
    "suffix,input_file_name,output_file_name,file_format,test_result_file_name",
    [
        ("make_wav", "test.mac", "test.wav", "bk_wav", "test.wav"),
        ("make_wav", "test", "test.wav", "bk_wav", "test.wav"),
        ("make_wav 'test2.wav'", "test.mac", "test2.wav", "bk_wav", "test2.wav"),
        ("make_wav 'test2.wav', 'test2'", "test.mac", "test2.wav", "bk_wav", "test2.wav"),
        ("make_wav 'test2'", "test.mac", "test2", "bk_wav", "test2.wav"),
        ("make_wav", "dir/test.mac", "dir/test.wav", "bk_wav", "test.wav"),

        ("make_turbo_wav", "test.mac", "test.wav", "bk_turbo_wav", "test.turbo.wav"),
        ("make_turbo_wav 'test2.wav'", "test.mac", "test2.wav", "bk_turbo_wav", "test2.turbo.wav"),
        ("make_turbo_wav", "dir/test.mac", "dir/test.wav", "bk_turbo_wav", "test.turbo.wav")
    ]
)
def test_wavs1(fs, suffix, input_file_name, output_file_name, file_format, test_result_file_name):
    fs.create_file(output_file_name)
    assert compile_and_emit(input_file_name, "mov r1, r2\n" + suffix) == (True, {"format": file_format, "path": output_file_name})
    with open(output_file_name, "rb") as f:
        assert f.read() == resources[test_result_file_name]

def test_wavs2(fs):
    compile("make_wav 'test.wav', '16 char long str'")
    compile("make_wav '16 char long str.wav'")
    with util.expect_error("too-long-string"):
        compile("make_wav 'test.wav', '17charslongstring'")
    with util.expect_error("too-long-string"):
        compile("make_wav '17charslongstring.wav'")


def test_link():
    expect_binary(".word .", b"\x00\x02")
    expect_binary(".link 1000\n.word .", b"\x00\x02")
    expect_binary(".link 2000\n.word .", b"\x00\x04")
    expect_binary(".link 0\n.word .", b"\x00\x00")

    with util.expect_error("address-conflict"):
        compile(".link 1000\n.link 2000")

    with util.expect_error("address-conflict"):  # maybe this is ok, idk
        compile(".link 1000\n.link 1000")

    with util.expect_error("recursive-definition"):  # maybe this is ok, idk
        compile(".link a\na = .")
    # TODO: check something like
    # .link a4
    # if a3 == 1000 { a4 = 1000 }
    # if a2 == 1000 { a3 = 1000 }
    # if a1 == 1000 { a2 = 1000 }
    # a1 = 1000


def test_encoding():
    with util.expect_error("invalid-character"):
        expect_same("clr r0\n.ascii /Hello α world/\nclr r1", "clr r0\nclr r1")
    with util.expect_error("invalid-character"):
        expect_same("clr r0\n.asciz /Hello α world/\nclr r1", "clr r0\nclr r1")

    compile("make_wav '16 char long str.wav'", output_charset="utf-8")
    compile("make_wav '16-карлонгстринг.wav'", output_charset="bk")
    with util.expect_error("too-long-string"):
        compile("make_wav '16-карлонгстринг.wav'", output_charset="utf-8")
    with util.expect_error("too-long-string"):
        compile("make_wav '17charslongstring.wav'", output_charset="utf-8")

    compile("make_wav '16 char long str.wav'", output_charset="utf-8")
    compile("make_wav 'abcdefghijklmnα.wav'", output_charset="utf-8")
    with util.expect_error("too-long-string"):
        compile("make_wav 'abcdefghijklmnoα.wav'", output_charset="utf-8")

    with util.expect_error("invalid-character"):
        expect_same("clr @#'α\nclr r1", "clr @#0\nclr r1")
    expect_binary(".word 'α", b"\xce\xb1", output_charset="utf-8")
    with util.expect_error("too-long-string"):
        expect_binary(".word '字", "字".encode()[:2], output_charset="utf-8")


def test_include(fs):
    fs.create_file("unreadable_file", st_mode=0)
    with util.expect_error("io-error"):
        compile(".include /unreadable_file/")

    fs.create_dir("test_dir")
    with util.expect_error("io-error"):
        compile(".include /test_dir/")

    with util.expect_error("io-error"):
        compile(".include /non_existant_file/")

    fs.create_file("included.mac", contents=".word .\n.ascii /Hello, world!/")
    expect_binary(".ascii /start /\n.include /included.mac/\n.ascii /end/", b"start \x06\x02Hello, world!end")

    # .link in included file should not affect root file
    fs.create_file("included_link.mac", contents=".link 2000\n.word .\n.ascii /Hello, world!/")
    # TODO: does not work yet
    # with util.expect_warning("include-link"):
    #     expect_binary(".ascii /start /\n.include /included_link.mac/\n.ascii /end/\n.word .", b"start \x00\x04Hello, world!end\x18\x02")
    expect_binary(".ascii /start /\n.include /included_link.mac/\n.ascii /end/\n.word .\n.link 3000", b"start \x00\x04Hello, world!end\x18\x06")



@pytest.mark.parametrize("declaration", ["a = 1", "a:"])
@pytest.mark.parametrize(
    "included_code,main_code",
    [
        (".extern a {}", "<> .word a"),
        ("{} .extern a", "<> .word a"),
        (".extern all {}", "<> .word a"),
        ("{} .extern all", "<> .word a"),
        (".extern a {}", ".word a <>"),
        ("{} .extern a", ".word a <>"),
        (".extern all {}", ".word a <>"),
        ("{} .extern all", ".word a <>"),

        (".word a", ".extern a {} <>"),
        (".word a", ".extern a <> {}"),
        (".word a", "{} .extern a <>"),
        (".word a", "{} <> .extern a"),
        (".word a", "<> {} .extern a"),
        (".word a", "<> .extern a {}"),

        (".word a", ".extern all {} <>"),
        (".word a", ".extern all <> {}"),
        (".word a", "{} .extern all <>"),
        (".word a", "{} <> .extern all"),
        (".word a", "<> {} .extern all"),
        (".word a", "<> .extern all {}"),
    ]
)
def test_extern1(fs, declaration, included_code, main_code):
    included_code = included_code.replace("{}", f"\n{declaration}\n")
    main_code = main_code.replace("{}", f"\n{declaration}\n")

    fs.create_file("included_code.mac", contents=included_code)

    expect_same(
        main_code.replace("<>", "\n.include /included_code.mac/\n"),
        re.sub(r"\.extern \S+", "", main_code.replace("<>", f"\n{included_code}\n"))
    )
