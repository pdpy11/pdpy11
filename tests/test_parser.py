from pdp.parser import parse
from pdp.types import *


def expect_code(code, insns):
    assert parse("test.mac", code) == File("test.mac", CodeBlock(None, None, insns))


def c(fn):
    return lambda *args, **kwargs: fn(None, None, *args, **kwargs)

R0 = c(Register)("r0")
MINUS_ONE = c(Number)("-1")
ZERO = c(Number)("0")
ONE = c(Number)("1")
TWO = c(Number)("2")
THREE = c(Number)("3")
A = c(Symbol)("a")

def INSN(operands):
    return c(Instruction)(c(Symbol)("insn"), operands)

def test_parsing():
    expect_code("insn", [INSN([])])
    expect_code("insn r0", [INSN([c(AddressingModes.Register)(R0)])])
    expect_code("insn r0, r0", [INSN([c(AddressingModes.Register)(R0), c(AddressingModes.Register)(R0)])])
    expect_code("insn (r0)", [INSN([c(AddressingModes.RegisterDeferred)(R0)])])
    expect_code("insn (r0)+", [INSN([c(AddressingModes.Autoincrement)(R0)])])
    expect_code("insn -(r0)", [INSN([c(AddressingModes.Autodecrement)(R0)])])
    expect_code("insn @(r0)+", [INSN([c(AddressingModes.AutoincrementDeferred)(R0)])])
    expect_code("insn @-(r0)", [INSN([c(AddressingModes.AutodecrementDeferred)(R0)])])
    expect_code("insn @(r0)", [INSN([c(AddressingModes.IndexDeferred)(R0, ZERO)])])
    expect_code("insn 1(r0)", [INSN([c(AddressingModes.Index)(R0, ONE)])])
    expect_code("insn -1(r0)", [INSN([c(AddressingModes.Index)(R0, MINUS_ONE)])])
    expect_code("insn a(r0)", [INSN([c(AddressingModes.Index)(R0, A)])])
    expect_code("insn @1(r0)", [INSN([c(AddressingModes.IndexDeferred)(R0, ONE)])])
    expect_code("insn @-1(r0)", [INSN([c(AddressingModes.IndexDeferred)(R0, MINUS_ONE)])])
    expect_code("insn @a(r0)", [INSN([c(AddressingModes.IndexDeferred)(R0, A)])])
    expect_code("insn #1", [INSN([c(AddressingModes.Immediate)(ONE)])])
    expect_code("insn #-1", [INSN([c(AddressingModes.Immediate)(MINUS_ONE)])])
    expect_code("insn #a", [INSN([c(AddressingModes.Immediate)(A)])])
    expect_code("insn @#1", [INSN([c(AddressingModes.Absolute)(ONE)])])
    expect_code("insn @#-1", [INSN([c(AddressingModes.Absolute)(MINUS_ONE)])])
    expect_code("insn @#a", [INSN([c(AddressingModes.Absolute)(A)])])
    expect_code("insn @1", [INSN([c(AddressingModes.RelativeDeferred)(ONE)])])
    expect_code("insn @-1", [INSN([c(AddressingModes.RelativeDeferred)(MINUS_ONE)])])
    expect_code("insn @a", [INSN([c(AddressingModes.RelativeDeferred)(A)])])
    expect_code("insn 1", [INSN([c(AddressingModes.Relative)(ONE)])])
    expect_code("insn -1", [INSN([c(AddressingModes.Relative)(MINUS_ONE)])])
    expect_code("insn a", [INSN([c(AddressingModes.Relative)(A)])])


def test_multiline():
    expect_code("insn\ninsn2", [INSN([]), c(Instruction)(c(Symbol)("insn2"), [])])


def test_code_blocks():
    expect_code("insn a { b }", [INSN([c(AddressingModes.Relative)(A), c(CodeBlock)([c(Instruction)(c(Symbol)("b"), [])])])])
    expect_code("insn a {\nb\nc\n}", [INSN([c(AddressingModes.Relative)(A), c(CodeBlock)([c(Instruction)(c(Symbol)("b"), []), c(Instruction)(c(Symbol)("c"), [])])])])


def test_expressions():
    expect_code("insn #1 + 2", [INSN([c(AddressingModes.Immediate)(c(Operator)(ONE, TWO, "+"))])])
    expect_code("insn #1 * 2", [INSN([c(AddressingModes.Immediate)(c(Operator)(ONE, TWO, "*"))])])
    expect_code("insn #1 + 2 * 3", [INSN([c(AddressingModes.Immediate)(c(Operator)(ONE, c(Operator)(TWO, THREE, "*"), "+"))])])
    expect_code("insn #(1 + 2) * 3", [INSN([c(AddressingModes.Immediate)(c(Operator)(c(Operator)(ONE, TWO, "+"), THREE, "*"))])])
    expect_code("insn #1 * 2 + 3", [INSN([c(AddressingModes.Immediate)(c(Operator)(c(Operator)(ONE, TWO, "*"), THREE, "+"))])])
    expect_code("insn #1 * (2 + 3)", [INSN([c(AddressingModes.Immediate)(c(Operator)(ONE, c(Operator)(TWO, THREE, "+"), "*"))])])
    expect_code("insn #1 * 2 * 3", [INSN([c(AddressingModes.Immediate)(c(Operator)(c(Operator)(ONE, TWO, "*"), THREE, "*"))])])
