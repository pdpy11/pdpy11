from .context import Context
from . import reports


class Token:
    def __init__(self, ctx_start, ctx_end, *args, **kwargs):
        assert ctx_start is None or isinstance(ctx_start, Context)
        assert ctx_end is None or isinstance(ctx_end, Context)
        self.ctx_start = None if ctx_start is None else ctx_start.save()
        self.ctx_end = None if ctx_end is None else ctx_end.save()
        self.init(*args, **kwargs)

    def init(self):
        pass

    def token_text(self):
        return self.ctx_start.code[self.ctx_start.pos:self.ctx_end.pos]


class ExpressionToken(Token):
    def resolve(self, state):
        raise NotImplementedError()


class Instruction(Token):
    # pylint: disable=arguments-differ
    def init(self, name, operands):
        self.name = name
        self.operands = operands

    def __repr__(self):
        if self.operands:
            return f"{self.name} {', '.join(map(repr, self.operands))}"
        else:
            return f"{self.name}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.operands) == (rhs.name, rhs.operands)


class InstructionPointer(ExpressionToken):
    def __repr__(self):
        return "."

    def __eq__(self, rhs):
        return isinstance(rhs, type(self))

    def resolve(self, state):
        return state["emit_address"]


class ParenthesizedExpression(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"({self.expr})"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.expr == rhs.expr

    def resolve(self, state):
        return self.expr.resolve(state)


class Symbol(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name

    def __repr__(self):
        return self.name

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name

    def resolve(self, state):
        if self.name.lower() in ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc"):
            reports.error(
                (self.ctx_start, self.ctx_end, "A register cannot be used here. An integer or a symbol are expected")
            )
            raise reports.RecoverableError("A register is used as a symbol")
        if self.name in state["compiler"].symbols:
            symbol, value = state["compiler"].symbols[self.name]
        elif self.name in state["local_symbols"]:
            symbol, value = state["local_symbols"][self.name]
        else:
            # TODO: check if there's a local symbol with the same name defined out of scope
            reports.error(
                (self.ctx_start, self.ctx_end, f"Unknown label '{self.name}' is referenced here")
            )
            raise reports.RecoverableError(f"Unknown label '{self.name}'")
        if isinstance(symbol, Assignment):
            value = symbol.value.resolve(state)
        return value


class Label(Token):
    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name
        self.local: bool = name[0].isdigit()

    def __repr__(self):
        return f"{self.name}:"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name


class Assignment(Token):
    # pylint: disable=arguments-differ
    def init(self, name: Symbol, value):
        self.name: Symbol = name
        self.value = value

    def __repr__(self):
        return f"{self.name} = {self.value}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.value) == (rhs.name, rhs.value)


class CodeBlock(Token):
    # pylint: disable=arguments-differ
    def init(self, insns):
        self.insns = insns

    def __repr__(self):
        return "{ " + "; ".join(map(repr, self.insns)) + " }"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.insns == rhs.insns


class String(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, quote: str, string: str):
        self.quote: str = quote
        self.string: str = string

    def __repr__(self):
        return f"{self.quote}{self.string}{self.quote}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.string == rhs.string

    def resolve(self, state):
        return self.string


class Number(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, representation):
        self.representation = representation

    def __repr__(self):
        return f"{self.representation}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.representation == rhs.representation

    def resolve(self, state):
        if self.representation.endswith("."):
            return int(self.representation[:-1])
        else:
            return int(self.representation, 8)


class File:
    def __init__(self, filename, body):
        self.filename = filename
        self.body = body

    def __repr__(self):
        return f"<{self.filename}> {self.body}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.filename, self.body) == (rhs.filename, rhs.body)
