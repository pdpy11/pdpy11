import struct

from .context import Context
from .deferred import not_ready, Awaiting, wait
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

    def text(self):
        return self.ctx_start.code[self.ctx_start.pos:self.ctx_end.pos]

    def __eq__(self, rhs):
        raise NotImplementedError()  # pragma: no cover


class ExpressionToken(Token):
    def resolve(self, state):
        raise NotImplementedError()  # pragma: no cover


class Instruction(Token):
    # pylint: disable=arguments-differ
    def init(self, name, operands):
        self.name = name
        self.operands = operands

    def __repr__(self):
        res = f"{self.name!r}"

        operands = self.operands[:]
        code_block = None
        if operands and isinstance(operands[-1], CodeBlock):
            code_block = operands.pop()
        if operands:
            res += " " + ", ".join(map(repr, operands))
        if code_block is not None:
            res += " " + repr(code_block)
        return res

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
        return f"({self.expr!r})"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.expr == rhs.expr

    def resolve(self, state):
        return self.expr.resolve(state)


class BracketedExpression(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"<{self.expr!r}>"

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

    def _resolve(self, state):
        if self.name.lower() in ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc"):
            reports.error(
                "unexpected-register",
                (self.ctx_start, self.ctx_end, "A register cannot be used here. An integer or a symbol are expected")
            )
            raise reports.RecoverableError("A register is used as a symbol")

        compiler = state["compiler"]

        candidates = (
            state["local_symbol_prefix"] + self.name,
            state["internal_symbol_prefix"] + self.name
        )

        for name in candidates:
            if name in compiler.symbols:
                return compiler.symbols[name]

        extern_mapping = compiler.extern_symbols_mapping.get(self.name)
        if extern_mapping:
            extern = compiler.symbols.get(extern_mapping[1])
            if extern:
                return extern

        for name in candidates + (() if extern_mapping else (self.name,)):
            if name not in compiler.on_symbol_defined_listeners:
                compiler.on_symbol_defined_listeners[name] = {}
            for elem in Awaiting.awaiting_stack[::-1]:
                compiler.on_symbol_defined_listeners[name][elem] = True  # Ordered set. Kinda.

        not_ready()
        # TODO: check if there's a local symbol with the same name defined out of scope
        reports.error(
            "undefined-symbol",
            (self.ctx_start, self.ctx_end, f"Unknown symbol '{self.name}' is referenced here")
        )
        return None, 0

    def resolve(self, state):
        return self._resolve(state)[1]

    def locate_definition(self, state):
        return self._resolve(state)[0]


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
        return f"{self.name!r} = {self.value!r}"

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


class AngleBracketedChar(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"<{self.expr!r}>"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.expr == rhs.expr

    def resolve(self, state):
        resolved = self.expr.resolve(state)
        # TODO: handle exception here
        return chr(wait(resolved))


class QuotedString(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, quote, string: str):
        self.quote: str = quote
        self.string: str = string

    def __repr__(self):
        return self.quote + self.string + self.quote

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.quote, self.string) == (rhs.quote, rhs.string)

    def resolve(self, state):
        return self.string


class StringConcatenation(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, chunks):
        self.chunks = chunks

    def __repr__(self):
        return " ".join(map(repr, self.chunks))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.chunks == rhs.chunks

    def resolve(self, state):
        return "".join(chunk.resolve(state) for chunk in self.chunks)


class Number(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, representation, value, invalid_base8=False):
        self.representation = representation
        self.value = value
        self.invalid_base8 = invalid_base8
        self.reported_invalid_base8 = False

    def __repr__(self):
        return f"{self.representation}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.representation, self.value, self.invalid_base8) == (rhs.representation, rhs.value, rhs.invalid_base8)

    def resolve(self, state):
        if not self.reported_invalid_base8 and self.invalid_base8:
            self.reported_invalid_base8 = True
            char = "8" if "8" in self.representation else "9"
            reports.error(
                "invalid-number",
                (self.ctx_start, self.ctx_end, f"In PDP-11 assembly, numbers are considered base-8 by default.\nThis number has digit {char}, so you probably wanted it base-10.\nAdd a dot after the number to switch to decimal: '{self.representation}.'\nIf you wanted to specify a local label of the same name, add a colon: '{self.representation}:'")
            )
        return self.value


class CharLiteral(ExpressionToken):
    # pylint: disable=arguments-differ
    def init(self, representation, string):
        self.representation = representation
        self.string = string
        self.evaluated_value = None

    def __repr__(self):
        return f"{self.representation}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.representation, self.string) == (rhs.representation, rhs.string)

    def resolve(self, state):
        if self.evaluated_value is not None:
            return self.evaluated_value

        try:
            bytes_value = self.string.encode(state["compiler"].output_charset)
        except UnicodeEncodeError as ex:
            reports.error(
                "invalid-character",
                (self.ctx_start, self.ctx_end, f"Cannot encode this literal using the selected output charset:\n{ex}\nYou can change the charset using --charset CLI argument or '.charset' directive.")
            )
            self.evaluated_value = 0
            return 0

        if len(bytes_value) > 2:
            reports.error(
                "too-long-string",
                (self.ctx_start, self.ctx_end, f"These characaters, encoded to {state['compiler'].output_charset}, take {len(bytes_value)} bytes, which does not fit in 16 bits.\nPlease fix that. Changing the encoding via '.charset ???' directive or '--charset=???' CLI argument may help.")
            )

        bytes_value = bytes_value[:2].ljust(2, b"\x00")
        self.evaluated_value = struct.unpack("<H", bytes_value)[0]
        return self.evaluated_value



class File:
    def __init__(self, filename, body):
        self.filename = filename
        self.body = body

    def __repr__(self):
        return f"<{self.filename}> {self.body!r}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.filename, self.body) == (rhs.filename, rhs.body)
