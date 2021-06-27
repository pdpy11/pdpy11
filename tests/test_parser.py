import pytest

from pdp.operators import *
from pdp.parser import parse
from pdp.types import *
from pdp import reports


def report_handler(priority, *reports):
    raise Exception(reports)


def expect_code(code, insns):
    with reports.handle_reports(report_handler):
        assert parse("test.mac", code) == File("test.mac", CodeBlock(None, None, insns))


def c(fn):
    return lambda *args, **kwargs: fn(None, None, *args, **kwargs)

R0 = c(Symbol)("r0")
MINUS_ONE = c(Number)("-1")
ZERO = c(Number)("0")
ONE = c(Number)("1")
TWO = c(Number)("2")
THREE = c(Number)("3")
A = c(Symbol)("a")
B = c(Symbol)("b")
C = c(Symbol)("c")
DOT = c(InstructionPointer)()
paren = c(ParenthesizedExpression)

def INSN(operands):
    return c(Instruction)(c(Symbol)("insn"), operands)


def test_instruction():
    expect_code("insn", [INSN([])])
    expect_code("insn r0", [INSN([R0])])
    expect_code("insn r0, r0", [INSN([R0, R0])])
    expect_code("insn (r0)", [INSN([paren(R0)])])
    expect_code("insn (r0)+", [INSN([c(postadd)(paren(R0))])])
    expect_code("insn -(r0)", [INSN([c(neg)(paren(R0))])])
    expect_code("insn @(r0)+", [INSN([c(deferred)(c(postadd)(paren(R0)))])])
    expect_code("insn @-(r0)", [INSN([c(deferred)(c(neg)(paren(R0)))])])
    expect_code("insn @(r0)", [INSN([c(deferred)(paren(R0))])])


@pytest.mark.parametrize(
    "expr_code,expr_value",
    [
        ("1", ONE),
        ("-1", MINUS_ONE),
        ("a", A),
        ("(1)", paren(ONE)),
        ("(-1)", paren(MINUS_ONE)),
        ("(a)", paren(A)),
        (".", DOT)
    ]
)
@pytest.mark.parametrize(
    "prefix_code,postfix_code,fn",
    [
        ("", "(r0)", lambda x: c(call)(x, R0)),
        ("@", "(r0)", lambda x: c(deferred)(c(call)(x, R0))),
        ("#", "", c(immediate)),
        ("@#", "", lambda x: c(deferred)(c(immediate)(x))),
        ("@", "", c(deferred)),
        ("", "", lambda x: x)
    ]
)
def test_expressions(expr_code, expr_value, prefix_code, postfix_code, fn):
    expect_code(f"insn {prefix_code}{expr_code}{postfix_code}", [INSN([fn(expr_value)])])


def test_multiline():
    expect_code("insn\ninsn2", [INSN([]), c(Instruction)(c(Symbol)("insn2"), [])])
    expect_code("insn 1\ninsn", [INSN([ONE]), INSN([])])


def test_code_blocks():
    expect_code("insn a { b }", [INSN([A, c(CodeBlock)([c(Instruction)(B, [])])])])
    expect_code("insn a {\nb\nc\n}", [INSN([A, c(CodeBlock)([c(Instruction)(B, []), c(Instruction)(C, [])])])])


@pytest.mark.parametrize(
    "a_code,a_value",
    [
        ("1", ONE),
        ("a", A),
        (".", DOT)
    ]
)
@pytest.mark.parametrize(
    "b_code,b_value",
    [
        ("2", TWO),
        ("b", B),
        (".", DOT)
    ]
)
def test_precedence_2(a_code, a_value, b_code, b_value):
    expect_code(f"insn #{a_code} + {b_code}", [INSN([c(immediate)(c(add)(a_value, b_value))])])
    expect_code(f"insn #{a_code} * {b_code}", [INSN([c(immediate)(c(mul)(a_value, b_value))])])
    expect_code(f"insn {a_code} + {b_code}", [INSN([c(add)(a_value, b_value)])])
    expect_code(f"insn {a_code} * {b_code}", [INSN([c(mul)(a_value, b_value)])])


def test_precedence_3():
    expect_code("insn #1 + 2 * 3", [INSN([c(immediate)(c(add)(ONE, c(mul)(TWO, THREE)))])])
    expect_code("insn #(1 + 2) * 3", [INSN([c(immediate)(c(mul)(paren(c(add)(ONE, TWO)), THREE))])])
    expect_code("insn #1 * 2 + 3", [INSN([c(immediate)(c(add)(c(mul)(ONE, TWO), THREE))])])
    expect_code("insn #1 * (2 + 3)", [INSN([c(immediate)(c(mul)(ONE, paren(c(add)(TWO, THREE))))])])
    expect_code("insn #1 * 2 * 3", [INSN([c(immediate)(c(mul)(c(mul)(ONE, TWO), THREE))])])


@pytest.mark.parametrize("code", ["1", "2", "0", "-1", "1.", "-1."])
def test_numbers(code):
    expect_code(f"insn #{code}", [INSN([c(immediate)(c(Number)(code))])])
