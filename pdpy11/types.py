import struct

from .context import Context
from .deferred import not_ready, Awaiting, wait
from . import reports


class Token:
    def __init__(self, ctx_start, ctx_end):
        assert ctx_start is None or isinstance(ctx_start, Context)
        assert ctx_end is None or isinstance(ctx_end, Context)
        self.ctx_start = None if ctx_start is None else ctx_start.save()
        self.ctx_end = None if ctx_end is None else ctx_end.save()

    def text(self):
        return self.ctx_start.code[self.ctx_start.pos:self.ctx_end.pos]

    def __eq__(self, rhs):
        raise NotImplementedError()  # pragma: no cover


class ExpressionToken(Token):
    def resolve(self, state):
        raise NotImplementedError()  # pragma: no cover


class Instruction(Token):
    def __init__(self, ctx_start, ctx_end, name, operands):
        super().__init__(ctx_start, ctx_end)
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


class WordList(Token):
    def __init__(self, ctx_start, ctx_end, words):
        super().__init__(ctx_start, ctx_end)
        self.words = words

    def __repr__(self):
        return ", ".join(map(repr, self.words))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.words == rhs.words


class InstructionPointer(ExpressionToken):
    def __repr__(self):
        return "."

    def __eq__(self, rhs):
        return isinstance(rhs, type(self))

    def resolve(self, state):
        return state["emit_address"]


class ParenthesizedExpression(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, expr, opening_parenthesis: str, closing_parenthesis: str):
        super().__init__(ctx_start, ctx_end)
        self.expr = expr
        self.opening_parenthesis: str = opening_parenthesis
        self.closing_parenthesis: str = closing_parenthesis

    def __repr__(self):
        return f"{self.opening_parenthesis}{self.expr!r}{self.closing_parenthesis}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.expr, self.opening_parenthesis, self.closing_parenthesis) == (rhs.expr, rhs.opening_parenthesis, rhs.closing_parenthesis)

    def resolve(self, state):
        return self.expr.resolve(state)


class Symbol(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, name: str, is_necessarily_label: bool=False):
        super().__init__(ctx_start, ctx_end)
        self.name: str = name
        self.is_necessarily_label: bool = is_necessarily_label

    def __repr__(self):
        return self.name + (":" if self.is_necessarily_label else "")

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.is_necessarily_label) == (rhs.name, rhs.is_necessarily_label)

    def _resolve(self, state):
        if self.name.lower() in ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc") and not self.is_necessarily_label:
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
    def __init__(self, ctx_start, ctx_end, name: str, is_extern: bool):
        super().__init__(ctx_start, ctx_end)
        self.name: str = name
        self.local: bool = name[0].isdigit()
        self.is_extern: bool = is_extern

    def __repr__(self):
        return f"{self.name}:" + (":" if self.is_extern else "")

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.is_extern) == (rhs.name, rhs.is_extern)


class Assignment(Token):
    def __init__(self, ctx_start, ctx_end, target: Symbol, value, is_extern: bool):
        super().__init__(ctx_start, ctx_end)
        self.target: Symbol = target
        self.value = value
        self.is_extern: bool = is_extern

    def __repr__(self):
        return f"{self.target!r} ={'=' if self.is_extern else ''} {self.value!r}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.target, self.value, self.is_extern) == (rhs.target, rhs.value, rhs.is_extern)


class CodeBlock(Token):
    def __init__(self, ctx_start, ctx_end, insns):
        super().__init__(ctx_start, ctx_end)
        self.insns = insns

    def __repr__(self):
        return "{ " + "; ".join(map(repr, self.insns)) + " }"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.insns == rhs.insns


class AngleBracketedChar(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, expr):
        super().__init__(ctx_start, ctx_end)
        self.expr = expr
        self.reported_error = False

    def __repr__(self):
        return f"<{self.expr!r}>"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.expr == rhs.expr

    def resolve(self, state):
        if self.reported_error:
            return ""

        from .metacommand_impl import get_as_int

        code = get_as_int(state, "Unicode code point", self, self.expr, bitness=None, unsigned=False)
        try:
            return chr(code)
        except ValueError:
            self.reported_error = True
            reports.error(
                "value-out-of-bounds",
                (self.ctx_start, self.ctx_end, f"<{code}> does not specify a valid Unicode code point because it's outside its range: [0; 0x110000).")
            )
            return ""


class QuotedString(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, quote, string: str):
        super().__init__(ctx_start, ctx_end)
        self.quote: str = quote
        self.string: str = string

    def __repr__(self):
        return self.quote + self.string + self.quote

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.quote, self.string) == (rhs.quote, rhs.string)

    def resolve(self, state):
        return self.string


class StringConcatenation(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, chunks):
        super().__init__(ctx_start, ctx_end)
        self.chunks = chunks

    def __repr__(self):
        return " ".join(map(repr, self.chunks))

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.chunks == rhs.chunks

    def resolve(self, state):
        from .metacommand_impl import get_as_str
        return "".join(get_as_str(state, "string chunk", self, chunk) for chunk in self.chunks)


class Number(ExpressionToken):
    def __init__(self, ctx_start, ctx_end, representation, value, is_valid_label, invalid_base8=False):
        super().__init__(ctx_start, ctx_end)
        self.representation = representation
        self.value = value
        self.is_valid_label = is_valid_label
        self.invalid_base8 = invalid_base8
        self.reported_invalid_base8 = False

    def __repr__(self):
        return f"{self.representation}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.representation, self.value, self.is_valid_label, self.invalid_base8) == (rhs.representation, rhs.value, rhs.is_valid_label, rhs.invalid_base8)

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
    def __init__(self, ctx_start, ctx_end, representation, string):
        super().__init__(ctx_start, ctx_end)
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
                (self.ctx_start, self.ctx_end, f"These characters, encoded to {state['compiler'].output_charset}, take {len(bytes_value)} bytes, which does not fit in 16 bits.\nPlease fix that. Changing the encoding via '.charset ???' directive or '--charset=???' CLI argument may help.")
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
