from .types import ExpressionToken


class InfixOperator(ExpressionToken):
    fn: ...
    char: str

    # pylint: disable=arguments-differ
    def init(self, lhs: ExpressionToken, rhs: ExpressionToken):
        self.lhs: ExpressionToken = lhs
        self.rhs: ExpressionToken = rhs

    def resolve(self, state):
        return type(self).fn(self.lhs.resolve(state), self.rhs.resolve(state))

    def __eq__(self, other):
        return isinstance(other, type(self)) and (self.lhs, self.rhs) == (other.lhs, other.rhs)

    def __repr__(self):
        return f"{self.lhs!r} {self.char} {self.rhs!r}"


class PrefixOperator(ExpressionToken):
    fn: ...
    char: str

    # pylint: disable=arguments-differ
    def init(self, operand: ExpressionToken):
        self.operand: ExpressionToken = operand

    def resolve(self, state):
        return type(self).fn(self.operand.resolve(state))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.operand == rhs.operand

    def __repr__(self):
        return f"{self.char}{self.operand!r}"


class PostfixOperator(ExpressionToken):
    fn: ...
    char: str

    # pylint: disable=arguments-differ
    def init(self, operand: ExpressionToken):
        self.operand: ExpressionToken = operand

    def resolve(self, state):
        return type(self).fn(self.operand.resolve(state))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.operand == rhs.operand

    def __repr__(self):
        return f"{self.operand!r}{self.char}"


operators = {
    InfixOperator: {},
    PrefixOperator: {},
    PostfixOperator: {}
}


def operator(signature, precedence, associativity):
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

    class Class(kind):
        pass
    Class.precedence = precedence
    Class.associativity = associativity
    Class.char = char
    operators[kind][char] = Class

    def decorator(fn):
        Class.fn = fn
        Class.__name__ = fn.__name__
        return Class

    return decorator


@operator("x+", precedence=3, associativity="left")
def postadd(x):
    raise NotImplementedError()


@operator("x-", precedence=3, associativity="left")
def postsub(x):
    raise NotImplementedError()


@operator("+x", precedence=3, associativity="left")
def pos(x):
    return +x


@operator("-x", precedence=3, associativity="left")
def neg(x):
    return -x


@operator("x * x", precedence=5, associativity="left")
def mul(a, b):
    return a * b


@operator("x / x", precedence=5, associativity="left")
def div(a, b):
    return a // b


@operator("x + x", precedence=6, associativity="left")
def add(a, b):
    return a + b


@operator("x - x", precedence=6, associativity="left")
def sub(a, b):
    return a - b


@operator("#x", precedence=17, associativity="left")
def immediate(x):
    raise NotImplementedError()


@operator("@x", precedence=17, associativity="left")
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
