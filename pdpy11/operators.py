import typing

from .containers import CaseInsensitiveDict
from .deferred import wait, Deferred, BaseDeferred
from .types import ExpressionToken


class InfixOperator(ExpressionToken):
    fn: ...
    char: str
    awaited: bool
    return_type: type

    # pylint: disable=arguments-differ
    def init(self, lhs: ExpressionToken, rhs: ExpressionToken):
        self.lhs: ExpressionToken = lhs
        self.rhs: ExpressionToken = rhs

    def resolve(self, state):
        lhs = self.lhs.resolve(state)
        rhs = self.rhs.resolve(state)
        if not isinstance(lhs, BaseDeferred) and not isinstance(rhs, BaseDeferred):
            return type(self).fn(lhs, rhs)
        if self.awaited:
            return Deferred[self.return_type](lambda: type(self).fn(wait(lhs), wait(rhs)))
        else:
            return Deferred[self.return_type](lambda: type(self).fn(lhs, rhs))

    def __eq__(self, other):
        return isinstance(other, type(self)) and (self.lhs, self.rhs) == (other.lhs, other.rhs)

    def __repr__(self):
        return f"{self.lhs!r} {self.char} {self.rhs!r}"


class UnaryOperator(ExpressionToken):
    fn: ...
    char: str
    awaited: bool
    return_type: type

    # pylint: disable=arguments-differ
    def init(self, operand: ExpressionToken):
        self.operand: ExpressionToken = operand

    def resolve(self, state):
        operand = self.operand.resolve(state)
        if not isinstance(operand, BaseDeferred):
            return type(self).fn(operand)
        if self.awaited:
            return Deferred[self.return_type](lambda: type(self).fn(wait(operand)))
        else:
            return Deferred[self.return_type](lambda: type(self).fn(operand))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.operand == rhs.operand


class PrefixOperator(UnaryOperator):
    def __repr__(self):
        return f"{self.char}{self.operand!r}"


class PostfixOperator(UnaryOperator):
    def __repr__(self):
        return f"{self.operand!r}{self.char}"


operators = {
    InfixOperator: CaseInsensitiveDict(),
    PrefixOperator: CaseInsensitiveDict(),
    PostfixOperator: CaseInsensitiveDict()
}


def operator(signature, precedence, associativity, awaited=True):
    assert associativity in ("left", "right")

    if signature[0] == signature[-1] == "x":
        # Infix operator
        char = signature[1:-1].strip()
        kind = InfixOperator
    elif signature[-1] == "x":
        # Prefix operator
        char = signature[:-1].strip()
        kind = PrefixOperator
    elif signature[0] == "x":
        # Postfix operator
        char = signature[1:].strip()
        kind = PostfixOperator
    else:
        assert False  # pragma: no cover

    assert char, "Operator must not be empty"

    class Class(kind):
        pass
    Class.precedence = precedence
    Class.associativity = associativity
    Class.char = char
    Class.awaited = awaited
    operators[kind][char] = Class

    def decorator(fn):
        Class.fn = fn
        Class.__name__ = fn.__name__
        Class.return_type = typing.get_type_hints(fn).get("return")
        return Class

    return decorator


# Operators precedences are mostly copied from C

@operator("x+", precedence=2, associativity="left")
def postadd(x):
    raise NotImplementedError()


@operator("x-", precedence=2, associativity="left")
def postsub(x):
    raise NotImplementedError()


@operator("+x", precedence=2, associativity="left", awaited=False)
def pos(x: int) -> int:
    return +x


@operator("-x", precedence=2, associativity="left", awaited=False)
def neg(x: int) -> int:
    return -x


@operator("~x", precedence=2, associativity="left")
def inv(x: int) -> int:
    return ~x


@operator("^c x", precedence=2, associativity="left")
def inv2(x: int) -> int:
    return ~x


@operator("x * x", precedence=3, associativity="left", awaited=False)
def mul(a: int, b: int) -> int:
    return a * b


@operator("x / x", precedence=3, associativity="left")
def div(a: int, b: int) -> int:
    return a // b


@operator("x % x", precedence=3, associativity="left")
def mod(a: int, b: int) -> int:
    return a % b


@operator("x + x", precedence=4, associativity="left", awaited=False)
def add(a: int, b: int) -> int:
    return a + b


@operator("x - x", precedence=4, associativity="left", awaited=False)
def sub(a: int, b: int) -> int:
    return a - b


@operator("x << x", precedence=5, associativity="left", awaited=False)
def lshift(a: int, b: int) -> int:
    b = wait(b)
    assert b >= 0  # TODO: handle this
    return a * 2 ** b


@operator("x >> x", precedence=5, associativity="left", awaited=False)
def rshift(a: int, b: int) -> int:
    b = wait(b)
    assert b >= 0  # TODO: handle this
    if b == 0:
        return a
    else:
        return wait(a) >> b


# It seems they were running out of characters.
@operator("x _ x", precedence=5, associativity="left")
def lsh(a: int, b: int) -> int:
    if b >= 0:
        return a << b
    else:
        return a >> -b


@operator("x & x", precedence=8, associativity="left")
def and_(a: int, b: int) -> int:
    return a & b


@operator("x ^ x", precedence=9, associativity="left")
def xor(a: int, b: int) -> int:
    return a ^ b


@operator("x | x", precedence=10, associativity="left")
def or_(a: int, b: int) -> int:
    return a | b


@operator("x ! x", precedence=10, associativity="left")
def or2(a: int, b: int) -> int:
    return a | b


@operator("#x", precedence=15, associativity="left")
def immediate(x):
    raise NotImplementedError()


@operator("@x", precedence=15, associativity="left")
def deferred(x):
    raise NotImplementedError()


class call(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, callee: ExpressionToken, operand: ExpressionToken):
        self.callee: ExpressionToken = callee
        self.operand: ExpressionToken = operand

    def __repr__(self):
        return f"{self.callee!r}({self.operand!r})"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.callee, self.operand) == (rhs.callee, rhs.operand)

    def resolve(self, state):
        raise NotImplementedError(f"call.resolve: {self!r}")
