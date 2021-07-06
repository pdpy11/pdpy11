import pytest

from pdpy11.operators import *
from pdpy11.parser import parse as parse_
from pdpy11.types import *

from . import util


def parse(code):
    return parse_("test.mac", code)


def expect_code(code, *insns):
    assert parse(code) == File("test.mac", CodeBlock(None, None, list(insns)))


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
paren = lambda expr: c(ParenthesizedExpression)(expr)
angle = lambda expr: c(BracketedExpression)(expr)

def INSN(*operands):
    return c(Instruction)(c(Symbol)("insn"), list(operands))

def ASCII(*operands):
    return c(Instruction)(c(Symbol)(".ascii"), list(operands))


def test_instruction():
    expect_code("insn", INSN())
    expect_code("insn r0", INSN(R0))
    expect_code("insn r0, r0", INSN(R0, R0))
    expect_code("insn (r0)", INSN(paren(R0)))
    expect_code("insn (r0)+", INSN(c(postadd)(paren(R0))))
    expect_code("insn -(r0)", INSN(c(neg)(paren(R0))))
    expect_code("insn @(r0)+", INSN(c(deferred)(c(postadd)(paren(R0)))))
    expect_code("insn @-(r0)", INSN(c(deferred)(c(neg)(paren(R0)))))
    expect_code("insn @(r0)", INSN(c(deferred)(paren(R0))))


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
    expect_code(f"insn {prefix_code}{expr_code}{postfix_code}", INSN(fn(expr_value)))


def test_multiline():
    expect_code("insn\ninsn2", INSN(), c(Instruction)(c(Symbol)("insn2"), []))
    expect_code("insn 1\ninsn", INSN(ONE), INSN())


def test_code_blocks():
    expect_code("insn a { b }", INSN(A, c(CodeBlock)([c(Instruction)(B, [])])))
    expect_code("insn a {\nb\nc\n}", INSN(A, c(CodeBlock)([c(Instruction)(B, []), c(Instruction)(C, [])])))


def test_precedence_one():
    expect_code(f"insn +a-", INSN(c(postsub)(c(pos)(A))))
    expect_code(f"insn -a+", INSN(c(postadd)(c(neg)(A))))


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
    expect_code(f"insn #{a_code} {op_code} {b_code}", INSN(c(immediate)(c(op)(a_value, b_value))))
    expect_code(f"insn {a_code} {op_code} {b_code}", INSN(c(op)(a_value, b_value)))

    expect_code(f"insn +{a_code} {op_code} {b_code}", INSN(c(op)(c(pos)(a_value), b_value)))
    if not a_code.isdigit():
        expect_code(f"insn -{a_code} {op_code} {b_code}", INSN(c(op)(c(neg)(a_value), b_value)))
    expect_code(f"insn {a_code} {op_code} {b_code}+", INSN(c(op)(a_value, c(postadd)(b_value))))
    expect_code(f"insn {a_code} {op_code} {b_code}-", INSN(c(op)(a_value, c(postsub)(b_value))))


def test_precedence_three():
    expect_code("insn #1 + 2 * 3", INSN(c(immediate)(c(add)(ONE, c(mul)(TWO, THREE)))))
    expect_code("insn #1 * 2 + 3", INSN(c(immediate)(c(add)(c(mul)(ONE, TWO), THREE))))
    expect_code("insn #1 * 2 * 3", INSN(c(immediate)(c(mul)(c(mul)(ONE, TWO), THREE))))


def test_brackets():
    expect_code("insn #(1 + 2) * 3", INSN(c(immediate)(c(mul)(paren(c(add)(ONE, TWO)), THREE))))
    expect_code("insn #1 * (2 + 3)", INSN(c(immediate)(c(mul)(ONE, paren(c(add)(TWO, THREE))))))

    expect_code("insn #<1 + 2> * 3", INSN(c(immediate)(c(mul)(angle(c(add)(ONE, TWO)), THREE))))
    expect_code("insn #1 * <2 + 3>", INSN(c(immediate)(c(mul)(ONE, angle(c(add)(TWO, THREE))))))

    expect_code("insn (1)(2)", INSN(c(call)(paren(ONE), TWO)))
    expect_code("insn <1>(2)", INSN(c(call)(angle(ONE), TWO)))

    with util.expect_error("invalid-insn", "missing-whitespace"):
        expect_code("insn (1)<2>", INSN(c(call)(paren(ONE), TWO)))
    with util.expect_error("invalid-insn", "missing-whitespace"):
        expect_code("insn <1><2>", INSN(c(call)(angle(ONE), TWO)))


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
        ("0b10110", 0b10110),
        ("^X1f", 0x1f),
        ("^O57", 0o57),
        ("^B10110", 0b10110),
        ("^D57", 57),
        ("57", 0o57),
        ("057", 0o57)
    ]
)
def test_numbers1(code, value):
    expect_code(f"insn #{code}", INSN(c(immediate)(c(Number)(code, value))))

def test_numbers2():
    expect_code("insn #81", INSN(c(immediate)(c(Number)("81", 81, invalid_base8=True))))
    expect_code("insn #91", INSN(c(immediate)(c(Number)("91", 91, invalid_base8=True))))


@pytest.mark.parametrize("name", ["hello", "HELLO", "1", "0", "99", "12$", "a_"])
def test_labels(name):
    expect_code(f"{name}: insn\n{name}:", c(Label)(name), INSN(), c(Label)(name))
    if not name[0].isdigit():
        expect_code(f"insn {name}", INSN(c(Symbol)(name)))
    expect_code(f"insn {name}:", INSN(c(Symbol)(name)))


@pytest.mark.parametrize("name", ["hello", "HELLO", "val$", "a_"])
def test_assignment(name):
    expect_code(f"{name} = 1", c(Assignment)(c(Symbol)(name), ONE))
    expect_code(f"{name} = 1 + 2", c(Assignment)(c(Symbol)(name), c(add)(ONE, TWO)))


def test_comments():
    expect_code(f"a = 1 ; amazing, isn't it?", c(Assignment)(A, ONE))
    expect_code(f"a = 1\n; amazing, isn't it?", c(Assignment)(A, ONE))
    expect_code(f"a = 1\n; amazing, isn't it?\n; one more comment\nb = 2", c(Assignment)(A, ONE), c(Assignment)(B, TWO))


def test_context():
    # TODO: much more throughout tests
    parsed = parse(" insn\n   insn2")
    assert repr(parsed.body.insns[0].ctx_start) == "test.mac:1:2"
    assert repr(parsed.body.insns[0].ctx_end) == "test.mac:1:6"
    assert repr(parsed.body.insns[1].ctx_start) == "test.mac:2:4"
    assert repr(parsed.body.insns[1].ctx_end) == "test.mac:2:9"


def test_unexpected_reserved_name():
    with util.expect_warning("suspicious-name"):
        parse("mov: nop")
    with util.expect_warning("suspicious-name"):
        parse("fadd: nop")
    with util.expect_warning("suspicious-name"):
        parse("r0: nop")

    with util.expect_warning("suspicious-name"):
        parse("mov = 1")
    with util.expect_warning("suspicious-name"):
        parse("fadd = 1")
    with util.expect_warning("suspicious-name"):
        parse("r0 = 1")

    with util.expect_warning("suspicious-name"):
        parse("clr mov:")
    with util.expect_warning("suspicious-name"):
        parse("clr fadd:")
    with util.expect_warning("suspicious-name"):
        parse("clr r0:")

    with util.expect_warning("suspicious-name"):
        parse("insn mov, 1")
    with util.expect_warning("suspicious-name"):
        parse("nop mov, 1")

    with util.expect_warning("suspicious-name"):
        parse("mov clr, r1")

    with util.expect_warning("missing-newline"):
        parse("nop mov")
    with util.expect_warning("missing-newline"):
        parse("nop fadd")
    with util.expect_warning("suspicious-name"):
        parse("clr mov")
    with util.expect_warning("suspicious-name"):
        parse("clr fadd")
    parse("clr r0")

    with util.expect_warning("suspicious-name"):
        parse("r0")


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
        ("'x'", "x")
    ]
)
def test_string1(code, value):
    expect_code(f".ascii {code}", ASCII(c(QuotedString)(code[0], value)))


def test_string2():
    with util.expect_error("invalid-escape"):
        parse("s = '\\f")
    with util.expect_error("unterminated-string"):
        parse("s = '")
    with util.expect_error("unterminated-string"):
        parse(".ascii '")

    with util.expect_warning("excess-quote"):
        expect_code("insn \"a\"", INSN(c(CharLiteral)("\"a", "a")))
    with util.expect_warning("excess-quote"):
        expect_code("insn \" \"", INSN(c(CharLiteral)("\" ", " ")))
    with util.expect_warning("excess-quote"):
        expect_code("insn \"  \"", INSN(c(CharLiteral)("\"  ", "  ")))
    with util.expect_warning("excess-quote"):
        expect_code("insn \"\"", INSN(c(CharLiteral)("\"", "")))
    with util.expect_warning("excess-quote"):
        expect_code("insn 'a'", INSN(c(CharLiteral)("'a", "a")))
    with util.expect_warning("excess-quote"):
        expect_code("insn ' '", INSN(c(CharLiteral)("' ", " ")))
    with util.expect_warning("excess-quote"):
        expect_code("insn ''", INSN(c(CharLiteral)("'", "")))

    with util.expect_error("unterminated-string"):
        parse("s = \"a")

    expect_code(f".ascii /Hello/ <1> /world/", ASCII(c(StringConcatenation)([c(QuotedString)("/", "Hello"), c(AngleBracketedChar)(ONE), c(QuotedString)("/", "world")])))
    expect_code(f".ascii /Hello/<1>", ASCII(c(StringConcatenation)([c(QuotedString)("/", "Hello"), c(AngleBracketedChar)(ONE)])))
    expect_code(f".ascii <1>/world/", ASCII(c(StringConcatenation)([c(AngleBracketedChar)(ONE), c(QuotedString)("/", "world")])))
    expect_code(f".ascii <1>", ASCII(c(AngleBracketedChar)(ONE)))


@pytest.mark.parametrize("name", [".unknownmetacommand", "unknown_metacommand"])
def test_unknown_metacommand(name):
    for char in "'\"/":
        expect_code(f"{name} {char}Hello{char}", c(Instruction)(c(Symbol)(name), [c(QuotedString)(char, "Hello")]))
        expect_code(f"{name} {char}Hello{char} <1> {char}world{char}", c(Instruction)(c(Symbol)(name), [c(StringConcatenation)([c(QuotedString)(char, "Hello"), c(AngleBracketedChar)(ONE), c(QuotedString)(char, "world")])]))
    expect_code(f"{name} 1 + 2", c(Instruction)(c(Symbol)(name), [c(add)(ONE, TWO)]))
    expect_code(f"{name} a + b", c(Instruction)(c(Symbol)(name), [c(add)(A, B)]))


def test_insn_syntax():
    parse("insn #(1) nop")
    with util.expect_error("invalid-insn"):
        parse("insn,")
    with util.expect_warning("missing-whitespace"):
        parse("insn#1")
    with util.expect_error("missing-whitespace"):
        parse("insn #(1)nop")
    with util.expect_warning("missing-newline"):
        parse("insn .word 1")
    with util.expect_error("missing-newline", "invalid-insn"):
        parse("insn%")


def test_newlines():
    assert parse("insn\n1") == parse("insn 1")
    assert parse("insn\n@#1") == parse("insn @#1")
    assert parse("insn\n'x") == parse("insn 'x")
    assert parse("insn\n\"ab") == parse("insn \"ab")
    assert parse("insn\n^rabc") == parse("insn ^rabc")
    assert parse("insn\n(1)") == parse("insn (1)")
    assert parse("insn\n<1>") == parse("insn <1>")
