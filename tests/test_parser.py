import json
import pytest

from pdp.operators import *
from pdp.parser import parse
from pdp.types import *
from pdp import reports


def report_handler(priority, identifier, *reports):
    raise Exception(identifier)


def expect_code(code, insns):
    with reports.handle_reports(report_handler):
        assert parse("test.mac", code) == File("test.mac", CodeBlock(None, None, insns))


def c(fn):
    return lambda *args, **kwargs: fn(None, None, *args, **kwargs)

R0 = c(Symbol)("r0")
MINUS_ONE = c(Number)("-1", -1)
ZERO = c(Number)("0", 0)
ONE = c(Number)("1", 1)
TWO = c(Number)("2", 2)
THREE = c(Number)("3", 3)
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


def test_precedence_one():
    expect_code(f"insn +a-", [INSN([c(postsub)(c(pos)(A))])])
    expect_code(f"insn -a+", [INSN([c(postadd)(c(neg)(A))])])


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
@pytest.mark.parametrize(
    "op_code,op",
    [
        ("+", add),
        ("*", mul)
    ]
)
def test_precedence_two(a_code, a_value, b_code, b_value, op_code, op):
    expect_code(f"insn #{a_code} {op_code} {b_code}", [INSN([c(immediate)(c(op)(a_value, b_value))])])
    expect_code(f"insn {a_code} {op_code} {b_code}", [INSN([c(op)(a_value, b_value)])])

    expect_code(f"insn +{a_code} {op_code} {b_code}", [INSN([c(op)(c(pos)(a_value), b_value)])])
    if not a_code.isdigit():
        expect_code(f"insn -{a_code} {op_code} {b_code}", [INSN([c(op)(c(neg)(a_value), b_value)])])
    expect_code(f"insn {a_code} {op_code} {b_code}+", [INSN([c(op)(a_value, c(postadd)(b_value))])])
    expect_code(f"insn {a_code} {op_code} {b_code}-", [INSN([c(op)(a_value, c(postsub)(b_value))])])


def test_precedence_three():
    expect_code("insn #1 + 2 * 3", [INSN([c(immediate)(c(add)(ONE, c(mul)(TWO, THREE)))])])
    expect_code("insn #(1 + 2) * 3", [INSN([c(immediate)(c(mul)(paren(c(add)(ONE, TWO)), THREE))])])
    expect_code("insn #1 * 2 + 3", [INSN([c(immediate)(c(add)(c(mul)(ONE, TWO), THREE))])])
    expect_code("insn #1 * (2 + 3)", [INSN([c(immediate)(c(mul)(ONE, paren(c(add)(TWO, THREE))))])])
    expect_code("insn #1 * 2 * 3", [INSN([c(immediate)(c(mul)(c(mul)(ONE, TWO), THREE))])])


@pytest.mark.parametrize(
    "code,value",
    [
        ("1", 1),
        ("2", 2),
        ("0", 0),
        ("-1", -1),
        ("1.", 1),
        ("-1.", -1),
        ("0x1f", 0x1f),
        ("-0x1f", -0x1f),
        ("0o57", 0o57),
        ("0b10110", 0b10110)
    ]
)
def test_numbers(code, value):
    expect_code(f"insn #{code}", [INSN([c(immediate)(c(Number)(code, value))])])

def test_numbers2():
    expect_code("insn #81", [INSN([c(immediate)(c(Number)("81", 81, invalid_base8=True))])])
    expect_code("insn #91", [INSN([c(immediate)(c(Number)("91", 91, invalid_base8=True))])])


@pytest.mark.parametrize(
    "code,value",
    [
        (r'"hello"', "hello"),
        (r'""', ""),
        (r'"aba caba"', "aba caba"),
        (r'"\""', "\""),
        (r'"\'"', "'"),
        (r'"/"', "/"),
        (r'"\x00"', "\x00"),
        (r'"\x01"', "\x01"),
        (r'"\xff"', "\xff"),
        (r'" \xff "', " \xff "),
        (r'"wow\\oh"', "wow\\oh"),
        (r'"amazing\ncode"', "amazing\ncode"),
        (r'"amazing \n code"', "amazing \n code"),
        (r'"\t"', "\t"),
        (r'"\r"', "\r"),
        (r'"\n"', "\n"),
        ('"a\\\nb"', "ab"),
        ("'x", "x")
    ]
)
def test_string(code, value):
    expect_code(f"insn {code}", [INSN([c(String)(code[0], value)])])


@pytest.mark.parametrize("name", ["hello", "HELLO", "1", "0", "99", "12$", "a_"])
def test_labels(name):
    expect_code(f"{name}: insn\n{name}:", [c(Label)(name), INSN([]), c(Label)(name)])
    if not name[0].isdigit():
        expect_code(f"insn {name}", [INSN([c(Symbol)(name)])])
    expect_code(f"insn {name}:", [INSN([c(Symbol)(name)])])


@pytest.mark.parametrize("name", ["hello", "HELLO", "val$", "a_"])
def test_assignment(name):
    expect_code(f"{name} = 1", [c(Assignment)(c(Symbol)(name), ONE)])
    expect_code(f"{name} = 1 + 2", [c(Assignment)(c(Symbol)(name), c(add)(ONE, TWO))])
