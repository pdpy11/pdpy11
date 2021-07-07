import re

from .builtins import builtin_commands, Metacommand
from .context import Context
from . import operators
from . import radix50
from . import reports
from . import types


class Goto(BaseException):
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, exc_tb):
        return exc_type is Goto
goto = Goto()


REGISTER_NAMES = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc")


class Parser:
    def __init__(self, fn):
        self.fn = fn


    @classmethod
    def either(cls, parsers):
        def fn(ctx):
            for parser in parsers:
                result = parser(ctx, maybe=True)
                if result is not None:
                    return result
            raise reports.RecoverableError("Failed to match either of the alternatives")
        return cls(fn)


    def __or__(self, rhs):
        assert isinstance(rhs, Parser)
        def fn(ctx):
            result = self(ctx, maybe=True)
            if result is not None:
                return result
            return rhs(ctx)
        return Parser(fn)


    def __add__(self, rhs):
        assert isinstance(rhs, Parser)
        def fn(ctx):
            result = self(ctx)
            rhs(ctx)
            return result
        return Parser(fn)


    def __invert__(self):
        def fn(ctx):
            if self(ctx, maybe=True):
                raise reports.RecoverableError("An unexpected match happened")
            return ""
        return Parser(fn)


    # def __rshift__(self, rhs):
    #     def fn(ctx):
    #         ctx_start = ctx.save()
    #         ctx_start.skip_whitespace()
    #         result = self(ctx)
    #         return rhs(ctx_start, ctx, result)
    #     return Parser(fn)


    def __call__(self, ctx, *, maybe=False, lookahead=False, report=None, **kwargs):
        if lookahead:
            assert maybe
        if maybe:
            old_ctx = ctx.save()
            try:
                result = self.fn(ctx, **kwargs)
                assert result is not None
            except reports.RecoverableError:
                ctx.restore(old_ctx)
                return None
            else:
                if lookahead:
                    ctx.restore(old_ctx)
                return result
        else:
            try:
                result = self.fn(ctx, **kwargs)
                assert result is not None
                return result
            except reports.RecoverableError:
                if report is None:
                    raise
                else:
                    reports.emit_report(*report)
                    return None


    @classmethod
    def regex(cls, regex, skip_whitespace_before=True, case_sensitive=False):
        regex = re.compile(regex, flags=0 if case_sensitive else re.I)
        def fn(ctx):
            if skip_whitespace_before:
                ctx.skip_whitespace()
            match = regex.match(ctx.code, ctx.pos)
            if match is None:
                raise reports.RecoverableError(f"Failed to match regex at position {ctx.pos}")
            ctx.pos = match.end()
            return match.group()
        return Parser(fn)


    @classmethod
    def literal(cls, literal, skip_whitespace_before=True, case_sensitive=False):
        if not case_sensitive:
            literal = literal.lower()
        def fn(ctx):
            if skip_whitespace_before:
                ctx.skip_whitespace()
            found = ctx.code[ctx.pos:ctx.pos + len(literal)]
            check_found = found if case_sensitive else found.lower()
            if check_found == literal:
                ctx.pos += len(literal)
                return literal
            else:
                raise reports.RecoverableError(f"Failed to match literal at position {ctx.pos}")
        return Parser(fn)


@Parser
def eof(ctx):
    ctx.skip_whitespace()
    if ctx.pos < len(ctx.code):
        raise reports.RecoverableError("Failed to match EOF")
    return True


newline = Parser.regex(r"\s*\n|\s*;[^\n]*", skip_whitespace_before=False)
comma = Parser.literal(",")
opening_parenthesis = Parser.literal("(")
closing_parenthesis = Parser.literal(")")
opening_angle_bracket = Parser.literal("<")
closing_angle_bracket = Parser.literal(">")
opening_bracket = Parser.literal("{")
closing_bracket = Parser.literal("}")
plus = Parser.literal("+")
minus = Parser.literal("-")
colon = Parser.literal(":")
at_sign = Parser.literal("@")
hash_sign = Parser.literal("#")
equals_sign = Parser.literal("=")
single_quote = Parser.literal("'")
double_quote = Parser.literal("\"")
string_quote = Parser.regex(r"['\"/]")
character = Parser.regex(r"[\s\S]", skip_whitespace_before=False)
string_backslash = Parser.literal("\\", skip_whitespace_before=False)


local_symbol_literal = Parser.regex(r"\d[a-z_0-9$]*")
symbol_literal = Parser.regex(r"[a-z_$][a-z_0-9$]*")
instruction_name = Parser.regex(r"\.?[a-z_][a-z_0-9]*")


@Parser
def number(ctx):
    # TODO: Macro-11 supports ^B, ^O, ^D, ^X standing for binary, octal, decimal and hexadecimal
    # TODO: Macro-11 supports ^R for radix-50. ^R<...> works, ^R^/.../ works, maybe something else works too
    # TODO: Macro-11 supports ^F... for floating-point numbers, no idea how the format looks like
    # TODO: Macro-11 supports ^P for psect limits, whatever that means

    negative = minus(ctx, maybe=True)
    sign = -1 if negative else 1
    sign_str = "-" if negative else ""

    ctx.skip_whitespace()
    ctx_start = ctx.save()

    boundary = r"(?![$_])\b"

    if Parser.literal("^X")(ctx, maybe=True):
        # Hexadimical number
        num = Parser.regex(rf"[0-9a-f]+{boundary}", skip_whitespace_before=False)(ctx, report=(
            reports.critical,
            "invalid-number",
            (ctx_start, ctx, "A hexadecimal number was expected after '^X'")
        ))
        return types.Number(ctx_start, ctx, f"{sign_str}^X{num}", int(num, 16) * sign)
    elif Parser.literal("^O")(ctx, maybe=True):
        # Octal number
        num = Parser.regex(rf"[0-7]+{boundary}", skip_whitespace_before=False)(ctx, report=(
            reports.critical,
            "invalid-number",
            (ctx_start, ctx, "An octal number was expected after '^O'")
        ))
        return types.Number(ctx_start, ctx, f"{sign_str}^O{num}", int(num, 8) * sign)
    elif Parser.literal("^B")(ctx, maybe=True):
        # Binary number
        num = Parser.regex(rf"[01]+{boundary}", skip_whitespace_before=False)(ctx, report=(
            reports.critical,
            "invalid-number",
            (ctx_start, ctx, "A binary number was expected after '^B'")
        ))
        return types.Number(ctx_start, ctx, f"{sign_str}^B{num}", int(num, 2) * sign)
    elif Parser.literal("^D")(ctx, maybe=True):
        # Decimal number
        num = Parser.regex(rf"\d+{boundary}", skip_whitespace_before=False)(ctx, report=(
            reports.critical,
            "invalid-number",
            (ctx_start, ctx, "A decimal number was expected after '^D'")
        ))
        return types.Number(ctx_start, ctx, f"{sign_str}^D{num}", int(num, 10) * sign)


    first_digit = Parser.regex(r"\d")(ctx)

    if first_digit == "0":
        if Parser.literal("x", skip_whitespace_before=False)(ctx, maybe=True):
            # Hexadecimal number
            num = Parser.regex(rf"[0-9a-f]+{boundary}", skip_whitespace_before=False)(ctx, report=(
                reports.critical,
                "invalid-number",
                (ctx_start, ctx, "A hexadecimal number was expected after '0x'")
            ))
            return types.Number(ctx_start, ctx, f"{sign_str}0x{num}", int(num, 16) * sign)
        elif Parser.literal("o", skip_whitespace_before=False)(ctx, maybe=True):
            # Octal number
            num = Parser.regex(rf"[0-7]+{boundary}", skip_whitespace_before=False)(ctx, report=(
                reports.critical,
                "invalid-number",
                (ctx_start, ctx, "An octal number was expected after '0o'")
            ))
            return types.Number(ctx_start, ctx, f"{sign_str}0o{num}", int(num, 8) * sign)
        elif Parser.literal("b", skip_whitespace_before=False)(ctx, maybe=True):
            # Binary number
            num = Parser.regex(rf"[01]+{boundary}", skip_whitespace_before=False)(ctx, report=(
                reports.critical,
                "invalid-number",
                (ctx_start, ctx, "A binary number was expected after '0b'")
            ))
            return types.Number(ctx_start, ctx, f"{sign_str}0b{num}", int(num, 2) * sign)

    # This may be a local label, so better not be strict
    num = Parser.regex(rf"\d*(\.|{boundary})", skip_whitespace_before=False)(ctx)
    num = first_digit + num

    if num.endswith("."):
        return types.Number(ctx_start, ctx, f"{sign_str}{num}", int(num[:-1], 10) * sign)

    if colon(ctx, maybe=True):
        raise reports.RecoverableError("Local label, not a number")

    if "8" in num or "9" in num:
        return types.Number(ctx_start, ctx, f"{sign_str}{num}", int(num, 10) * sign, invalid_base8=True)

    return types.Number(ctx_start, ctx, f"{sign_str}{num}", int(num, 8) * sign)


radix50_chars = Parser.regex("[" + re.escape(radix50.TABLE.replace(" ", "")) + "]+", skip_whitespace_before=False)

@Parser
def radix50_literal(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    Parser.literal("^R")(ctx)

    string = radix50_chars(ctx, report=(
        reports.error,
        "invalid-string",
        (ctx_start, ctx, "Up to three radix-50 characters are expected after ^R.")
    ))
    if string is None:
        string = ""

    if len(string) > 3:
        reports.error(
            "invalid-string",
            (ctx_start, ctx, f"This radix-50 literal contains more than 3 characters ({len(string)}, in particular).")
        )
        string = string[:3]

    string = string.upper()

    return types.Number(ctx_start, ctx, f"^R{string}", radix50.pack_to_int(string))


@Parser
def label(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    name = Parser.regex(r"([a-z_0-9$]+)\s*:")(ctx)
    name = name[:-1].strip()

    if name in builtin_commands:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a label definition.\nPlease consider changing the label not to look like an instruction")
        )
    elif name.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "Label name clashes with a register.\nYou won't be able to access this label because every usage would be parsed as a register.")
        )

    return types.Label(ctx_start, ctx, name)


@Parser
def assignment(ctx):
    # TODO: Macro-11 supports '. = X' syntax which we should probably interpret
    # as an alias for '.blkb X - .'. Or as '.link X' if nothing has been emitted
    # yet.

    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx)
    ctx_after_symbol = ctx.save()
    ctx.skip_whitespace()

    ctx_equals = ctx.save()
    equals_sign(ctx)
    ctx_after_equals = ctx.save()
    ctx.skip_whitespace()

    value = expression(ctx, report=(
        reports.critical,
        "invalid-assignment",
        (ctx_equals, ctx_after_equals, "An equals sign '=' must be followed by an expression (as in assignment)"),
        (ctx, ctx, "...yet no expression was matched here")
    ))

    if symbol in builtin_commands:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a constant definition.\nPlease consider changing the constant name not to look like an instruction")
        )
    elif symbol.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx_after_symbol, f"Symbol name clashes with a register.\nYou won't be able to access this symbol because every usage would be parsed as a register.\nMaybe you are unfamiliar with assembly and wanted to say 'mov #{value!r}, {symbol}'?")
        )

    return types.Assignment(ctx_start, ctx, types.Symbol(ctx_start, ctx_after_symbol, symbol), value)


@Parser
def symbol_expression(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx)
    if symbol in builtin_commands:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as an operand.\nCheck for a missing newline or an excess comma before it.")
        )

    if colon(ctx, maybe=True) and symbol.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles a register, but is parsed as a label.")
        )

    return types.Symbol(ctx_start, ctx, symbol)


@Parser
def local_symbol_expression(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    symbol = local_symbol_literal(ctx)
    colon(ctx, maybe=not symbol.isdigit())
    return types.Symbol(ctx_start, ctx, symbol)


@Parser
def string_escape(ctx):
    ctx_start = ctx.save()

    string_backslash(ctx)

    char = character(ctx, report=(
        reports.error,
        "invalid-escape",
        (ctx_start, ctx, "A letter is expected after a backslash '\\' in a string")
    )).lower()

    if char == "n":
        return "\n"
    elif char == "r":
        return "\r"
    elif char == "t":
        return "\t"
    elif char in "\\\"'/":
        return char
    elif char == "\n":
        return ""
    elif char == "x":
        num = Parser.regex(r"[0-9a-f]{2}")(ctx, report=(
            reports.error,
            "invalid-escape",
            (ctx_start, ctx, "Two hexadecimal digits are expected after '\\x' in a string")
        ))
        return chr(int(num, 16))
    else:
        reports.error(
            "invalid-escape",
            (ctx_start, ctx, f"Unknown escape '\\{char}' in a string")
        )
        return ""

string_char = string_escape | character


@Parser
def single_quoted_literal(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    single_quote(ctx)

    if ctx.pos == len(ctx.code) or ctx.code[ctx.pos] in "\t\r\n":
        reports.critical(
            "unterminated-string",
            (ctx_start, ctx, "Unterminated string literal. A single character is expected after '.")
        )

    value = ""
    if ctx.code[ctx.pos] != "'":
        value += string_char(ctx)

    if ctx.pos < len(ctx.code) and ctx.code[ctx.pos] == "'":
        single_quote(ctx)
        reports.warning(
            "excess-quote",
            (ctx_start, ctx, "Single quotation mark denotes not a string, but an ASCII value of a character.\nUnlike C, a character must not be terminated by a single quotation mark.\nFor example, 'a should be used instead of 'a'. " + ["An empty string can be safely replaced with a zero.", "Please remove the second quotation mark."][len(value)])
        )

    return types.CharLiteral(ctx_start, ctx, "'" + value, value)


@Parser
def double_quoted_literal(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    double_quote(ctx)

    value = ""

    for _ in range(2):
        if ctx.pos == len(ctx.code) or ctx.code[ctx.pos] in "\t\r\n":
            reports.critical(
                "unterminated-string",
                (ctx_start, ctx, "Unterminated string literal. Exactly two characters are expected after \".")
            )
        if ctx.code[ctx.pos] != "\"":
            value += string_char(ctx)

    if ctx.pos < len(ctx.code) and ctx.code[ctx.pos] == "\"":
        double_quote(ctx)
        reports.warning(
            "excess-quote",
            (ctx_start, ctx, "Double quotation mark does not denote a string. It denotes an ASCII conversion operator,\nwhich means that the two characters after \" are converted to a 16-bit word.\nFor example, \"AB is the same as 0x4142 (or ^H4142).\n" + ["An empty string, as here, can be safely replaced with a zero.", f"Exactly two characters are expected after the quotation mark, and the closing mark is unnecessary.\nPlease use '{value} instead.", f"Unlike C, this literal must not be terminated by a quotation mark -- please remove it: \"{value}"][len(value)])
        )

    return types.CharLiteral(ctx_start, ctx, "\"" + value, value)


@Parser
def quoted_string(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    quote = string_quote(ctx)
    value = ""
    while ctx.pos < len(ctx.code) and ctx.code[ctx.pos] != quote:
        value += string_char(ctx)

    if ctx.pos == len(ctx.code):
        reports.critical(
            "unterminated-string",
            (ctx_start, ctx, "Unterminated string literal")
        )

    ctx.pos += 1
    return types.QuotedString(ctx_start, ctx, quote, value)


@Parser
def angle_bracketed_char(ctx):
    ctx_start = ctx.save()
    opening_angle_bracket(ctx)
    expr = expression(ctx)
    closing_angle_bracket(ctx)
    return types.AngleBracketedChar(ctx_start, ctx, expr)


@Parser
def long_string(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    chunks = [(quoted_string | angle_bracketed_char)(ctx)]

    while True:
        chunk = (quoted_string | angle_bracketed_char)(ctx, maybe=True)
        if chunk is None:
            break
        chunks.append(chunk)

    if len(chunks) == 1:
        # For performance. Maybe.
        return chunks[0]
    else:
        return types.StringConcatenation(ctx_start, ctx, chunks)


# TODO: Terrible. Macro-11 supports 'x for single-character constants and
# "ab for two-character constants which are implicitly converted to a
# number, immediately. Other assemblers support closing quotes: 'x' and
# "ab".

# Old PDPy11 handles this in a different way, it requires closing quotes
# like 'x' and "ab", doesn't see any difference between ' and " and even
# allows longer strings. Then it supports /abacaba/ for strings which other
# assemblers (except maybe pdp11asm) don't support, and doesn't support
# ^/abacaba/ and <abacaba> which other compilers do support (although in
# a different context)

# Another problem is that the new assembler silently interprets #"a"+"b" as
# #"ab" while other assemblers (including older PDPy11, luckily) interpret
# it as #97.+98., because the new compiler supports + for concatenation. We
# should come up with a better solution.


# Now let's talk about 'bracketing'. Macro-11 supports two bracketing
# formats: <...> and ^/.../, in the latter case '/' may be any puncutation
# character, though '/' is much more common. In usual context, these two
# are the same and are used for the same purpose as parentheses in math.


# When Macro-11 expects a string (which happens after ^R (radix 50), .nchr,
# '.if b', '.if idn' and others, '=' in macro defaults, .irp and .irpc), the
# two types of brackets are redefined to contain a string. For example, all
# the following codes encode the string 'abacaba':
#   <abacaba>
#   ^/abacaba/
#   ^"abacaba"
#   ^,abacaba,
# Angle brackets can be nested, e.g. this encodes string 'aba<ca>ba':
#   <aba<ca>ba>
# If, however, neither ^ nor < are matched, it just assumes the next token
# (until whitespace, a comma or a semicolon) is the string contents.

# However!

# After .include and .library, the following formats are okay:
#   /abacaba/
#   "abacaba"
#   ,abacaba,
# But angle brackets and ^/.../ are not supported.

# After .ascii, .asciz and .rad50 it's almost the same as .include, but
# angle brackets are defined to encode single bytes. The following strings
# all decode to 'abacaba':
#   /abacaba/
#   "abacaba"
#   ,abacaba,
#   /aba/ <99.> /aba/


# The above means that we can no longer parse all instructions (meta- or
# not) the same way. This highlights a problem with macros because at
# parsing time we can no longer detect whether "ab" is a number or a string
# and whether "ab c" is a single string or two tokens and whether that
# causes a parsing error.



@Parser
def instruction_pointer(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    Parser.regex(r"\.(?![a-z_0-9])")(ctx)
    return types.InstructionPointer(ctx_start, ctx)

expression_literal = symbol_expression | radix50_literal | number | local_symbol_expression | single_quoted_literal | double_quoted_literal | instruction_pointer

infix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.InfixOperator]])
prefix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PrefixOperator]])
postfix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PostfixOperator]])
register_name = Parser.either([Parser.literal(reg) for reg in REGISTER_NAMES])


@Parser
def expression_literal_rec(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    if (opening_parenthesis | opening_angle_bracket)(ctx, maybe=True, lookahead=True):
        value = None
    else:
        value = expression_literal(ctx)

    while True:
        # <x> is allowed and means the same as (x)
        # (a)(b) is a call with callee (a) and operand b
        # <a>(b) is a call with callee <a> and operand b
        # (a)<b> is a syntax error
        # <a><b> is a syntax error too
        if value is None:
            bracket = (opening_parenthesis | opening_angle_bracket)(ctx, maybe=True)
        else:
            bracket = opening_parenthesis(ctx, maybe=True)
        if bracket is None:
            break

        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()

        expr = expression(ctx, report=(
            reports.critical,
            "invalid-expression",
            (ctx, ctx, "Could not parse an expression here"),
            (ctx_start, ctx_after_paren, "...as expected after an opening parenthesis here")
        ))

        ctx.skip_whitespace()

        (closing_parenthesis if bracket == "(" else closing_angle_bracket)(ctx, report=(
            reports.critical,
            "invalid-expression",
            (ctx, ctx, "This is not a operator, so a closing parenthesis is expected here"),
            (ctx_start, ctx_after_paren, "...to match an opening parenthesis here")
        ))

        if value is None:
            if bracket == "(":
                value = types.ParenthesizedExpression(ctx_start, ctx, expr)
            else:
                value = types.BracketedExpression(ctx_start, ctx, expr)
        else:
            value = operators.call(ctx_start, ctx, value, expr)

    return value


@Parser
def expression(ctx):
    op_stack = []

    ctx.skip_whitespace()
    ctx_start = ctx.save()
    ctx_op = ctx.save()

    # Try to match a full expression before matching a prefix operator, so that
    # -1 is parsed as -1, not -(1)
    while True:
        expr = expression_literal_rec(ctx, maybe=True)
        if expr is not None:
            break
        char = prefix_operator(ctx, report=(
            reports.critical,
            "invalid-expression",
            (ctx, ctx, "Expected an expression or an operator here"),
            (ctx_start, ctx, "...after a prefix here")
        ) if op_stack else None)
        op_stack.append({
            "ctx_start": ctx_op,
            "operator": operators.operators[operators.PrefixOperator][char]
        })
        ctx.skip_whitespace()
        ctx_op = ctx.save()

    stack = [expr]

    def pop_op_stack(ctx_end):
        info = op_stack.pop()
        operator = info["operator"]
        if issubclass(operator, operators.InfixOperator):
            rhs = stack.pop()
            lhs = stack.pop()
            stack.append(operator(lhs.ctx_start, ctx_end, lhs, rhs))
        else:
            op_operand = stack.pop()
            stack.append(operator(info["ctx_start"], ctx_end, op_operand))


    # TODO: Macro-11 doesn't support operator precedence, it evaluates infix
    # operators left to right. This may cause problems in code such as
    # '1 * 2 + 3' which Macro-11 evaluates to 11 (oct) and PDPy11 evaluates to
    # 5. We should emit a warning or handle this differently in Macro-11 and
    # pdp11asm compatibility modes.
    while True:
        ctx_prev = ctx.save()

        ctx.skip_whitespace()
        ctx_op = ctx.save()

        char = (postfix_operator + (newline | comma | closing_parenthesis | closing_bracket | eof))(ctx, maybe=True, lookahead=True)
        if char:
            # Postfix operator
            postfix_operator(ctx)
            ctx_op_end = ctx.save()

            operator = operators.operators[operators.PostfixOperator][char]

            self_precedence = operator.precedence
            is_left_associative = operator.associativity == "left"

            while op_stack and (self_precedence, is_left_associative) > (op_stack[-1]["operator"].precedence, False):
                pop_op_stack(ctx_prev)

            stack[-1] = operator(ctx_op, ctx_op_end, stack[-1])
            break
        else:
            # Must be an infix operator
            char = infix_operator(ctx, maybe=True)
            if not char:
                ctx.restore(ctx_prev)
                break

            ctx_op_end = ctx.save()

            operator = operators.operators[operators.InfixOperator][char]

            expr = expression_literal_rec(ctx, report=(
                reports.critical,
                "invalid-expression",
                (ctx, ctx, "Could not parse an expression here"),
                (ctx_op, ctx_op_end, f"...as expected after operator '{char}'")
            ))

            self_precedence = operator.precedence
            is_left_associative = operator.associativity == "left"

            while op_stack and (self_precedence, is_left_associative) > (op_stack[-1]["operator"].precedence, False):
                pop_op_stack(ctx_prev)

            stack.append(expr)
            op_stack.append({
                "operator": operator
            })

    while op_stack:
        pop_op_stack(ctx)

    return stack[-1]


@Parser
def register_literal(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    name = register_name(ctx)
    return types.Symbol(ctx_start, ctx, name)


@Parser
def autoincrement_addressing_operand(ctx):
    ctx_start = ctx.save()
    opening_parenthesis(ctx)
    reg = register_literal(ctx)
    closing_parenthesis(ctx)
    ctx_after_paren = ctx.save()
    plus(ctx)
    return operators.postadd(ctx_start, ctx, types.ParenthesizedExpression(ctx_start, ctx_after_paren, reg))


@Parser
def deferred_autoincrement_addressing_operand(ctx):
    ctx_start = ctx.save()
    at_sign(ctx)
    inner = autoincrement_addressing_operand(ctx)
    return operators.deferred(ctx_start, ctx, inner)


insn_operand = autoincrement_addressing_operand | deferred_autoincrement_addressing_operand | expression

def parse_insn_operand(ctx, insn_name, operand_idx, **kwargs):
    if insn_name in builtin_commands:
        insn = builtin_commands[insn_name]
    elif "." + insn_name in builtin_commands:
        # A warning will be emitted later by the compiler, no need to emit it
        # now
        insn = builtin_commands["." + insn_name]
    else:
        insn = None

    is_metacommand = (
        isinstance(insn, Metacommand)
        or (
            insn is None
            and (insn_name.startswith(".") or "_" in insn_name)
        )
    )

    if is_metacommand:
        if insn is not None and insn.operand_info:
            operand_type = insn.operand_info[min(operand_idx, len(insn.operand_info) - 1)]["type"]
        else:
            # If the metacommand doesn't take any operand but was somehow passed
            # one, we can only hope this invalid operand does not break the
            # parser. A similar situation is when we don't know that we have to
            # parse a metacommand we don't know about.
            #
            # The safest option seems to be to parse the operand as an
            # expression, except when it starts with ", ' or /, in which case we
            # parse it as a string.
            if string_quote(ctx, maybe=True, lookahead=True):
                operand_type = str
            else:
                operand_type = int
    else:
        operand_type = int

    assert operand_type in (str, int)

    if operand_type is str:
        return long_string(ctx, **kwargs)
    else:
        return insn_operand(ctx, **kwargs)


@Parser
def instruction(ctx):
    # TODO: Macro-11 supports .rem metacommand for comments, like this:
    #   .rem / My comment goes here
    #   still a comment
    #   comment closes here /
    # (the first character after '.rem' is a 'quotation' sign)

    ctx_start = ctx.save()
    insn_name = instruction_name(ctx)
    if insn_name.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "Instruction name suspiciously resembles a register.\nCheck for an excess newline or a missing comma before the register name")
        )
    ctx_state_after_name = ctx.save()
    insn_name_symbol = types.Symbol(ctx_start, ctx_state_after_name, insn_name)


    if insn_name in builtin_commands and isinstance(builtin_commands[insn_name], Metacommand) and builtin_commands[insn_name].literal_string_operand:
        idx = ctx.code.find("\n", ctx.pos)
        if idx == -1:
            idx = len(ctx.code)

        text = ctx.code[ctx.pos:idx].strip()
        if text:
            ctx.skip_whitespace()
            ctx_before_message = ctx.save()
            ctx.pos += len(text)
            operands = [types.QuotedString(ctx_before_message, ctx, "", text)]
        else:
            operands = []

        return types.Instruction(ctx_start, ctx, insn_name_symbol, operands)



    operands = []

    if comma(ctx, maybe=True, lookahead=True):
        ctx_before_comma = ctx.save()
        comma(ctx)
        reports.critical(
            "invalid-insn",
            (ctx_before_comma, ctx, "Unexpected comma right after instruction name; expected an operand"),
            (ctx_start, ctx_state_after_name, "Instruction started here")
        )

    with goto:
        if closing_bracket(ctx, maybe=True, lookahead=True):
            raise goto

        if newline(ctx, maybe=True, lookahead=True):
            # The recommended way to separate instructions is by newlines, e.g.
            #     mov r0, r1
            #     nop
            #     add r1, r2
            # Some old codes use spaces or tabs for that, so the code looks like
            #     mov r0, r1 nop add r1, r2
            # For a classic assemblers these two codes are equivalent, but pdpy
            # supports rather complex macros, which makes it difficult to figure
            # out at parse time whether e.g. 'insn insn' means two instructions
            # 'insn' in a row or instruction 'insn' with operand 'insn'.
            # Hence we have some sanity checks below to roll back to parsing a
            # zero-operand instruction if we detect that the first operand seems
            # to look like the next instruction.

            # Other programmers tend to add newlines when that is unnecessary
            # and even harmful, e.g.
            #     .byte
            #     x, y, z
            # which is parsed by some compilers as
            #     .byte x, y, z
            # and by others as
            #     .byte 0  # .byte without operands is .byte 0
            #     .word x, y, z  # implicit .word

            # The first interpretation is probably more correct, but the second
            # interpretation is more Macro-11 compatible.
            # TODO: assume the second interpretation (and raise a warning) in
            # Macro-11 compatibility mode

            if (radix50_literal | (number + ~colon) | single_quoted_literal | double_quoted_literal | prefix_operator | opening_parenthesis | opening_angle_bracket | (symbol_literal + comma))(ctx, maybe=True, lookahead=True):
                # All of these are invalid at the beginning of instruction, so
                # they are probably a continuation of the current instruction.
                # TODO: emit a warning?
                pass
            else:
                raise goto

        name = (instruction_name + ~colon)(ctx, maybe=True, lookahead=True)
        if name in builtin_commands and (insn_name not in builtin_commands or builtin_commands[insn_name].max_operands == 0):
            # Does not take an operand for sure
            ctx_new = ctx.save()
            ctx_new.skip_whitespace()
            ctx_before_insn = ctx_new.save()
            next_insn_name = instruction_name(ctx_new)
            if not (comma | infix_operator | postfix_operator)(ctx_new, maybe=True, lookahead=True):
                reports.warning(
                    "missing-newline",
                    (ctx_start, ctx_state_after_name, "There is no newline after the name of this instruction, hence an operand must follow,"),
                    (ctx_before_insn, ctx_new, f"but it suspiciously resembles another instruction.\nYou probably \x1b[3mmeant\x1b[23m an instruction '{insn_name}' without operands followed by a '{next_insn_name}' instruction,\nand pdpy will compile this code as such, but this is against standards; please add a newline between instructions.")
                )
                raise goto

        first_operand = parse_insn_operand(ctx, insn_name, 0, maybe=True)

        if first_operand:
            if ctx_state_after_name.pos < len(ctx.code) and ctx.code[ctx_state_after_name.pos].strip() != "":
                reports.warning(
                    "missing-whitespace",
                    (ctx_state_after_name, ctx, "Expected whitespace after instruction name. Proceeding under assumption that an operand follows.")
                )

            operands = [first_operand]

            ctx_before_comma = ctx.save()
            while comma(ctx, maybe=True):
                ctx_after_comma = ctx.save()
                ctx.skip_whitespace()
                oper = parse_insn_operand(ctx, insn_name, len(operands), report=(
                    reports.critical,
                    "invalid-operand",
                    (ctx_before_comma, ctx_after_comma, "Expected operand after comma in an instruction"),
                    (ctx_start, ctx_state_after_name, "(instruction started here)"),
                    (ctx, ctx, "This definitely does not look like an operand")
                ))
                operands.append(oper)
                ctx_before_comma = ctx.save()

            ctx_opening_bracket = ctx.save()
            if opening_bracket(ctx, maybe=True):
                oper = code(ctx, break_on_closing_bracket=True)
                oper.ctx = ctx_opening_bracket
                operands.append(oper)

            if ctx.pos < len(ctx.code) and ctx.code[ctx.pos].strip() not in ("", ";"):
                reports.error(
                    "missing-whitespace",
                    (ctx, ctx, "Expected whitespace after instruction. Proceeding as if a new instruction is starting")
                )
        else:
            if ctx_state_after_name.pos < len(ctx.code):
                ctx.skip_whitespace()
                reports.warning(
                    "missing-newline",
                    (ctx, ctx, "Could not parse an operand starting from here; assuming a new instruction.\nPlease add a newline here if an instruction was implied."),
                    (ctx_start, ctx_state_after_name, "The previous instruction started here")
                )

    return types.Instruction(ctx_start, ctx, insn_name_symbol, operands)


@Parser
def code(ctx, break_on_closing_bracket=False):
    ctx_start = ctx.save()

    insns = []

    while not ctx.eof():
        ctx.skip_whitespace()
        ctx_start = ctx.save()
        if break_on_closing_bracket and closing_bracket(ctx, maybe=True):
            break

        insn = (label | assignment | instruction)(ctx, report=(
            reports.critical,
            "invalid-insn",
            (ctx_start, ctx_start, "Could not parse instruction starting from here")
        ))
        insns.append(insn)

        if not break_on_closing_bracket and isinstance(insn, types.Instruction) and insn.name.name.lower() in ("end", ".end"):
            # Because some people add junk after .end
            break

    return types.CodeBlock(ctx_start, ctx, insns)


def parse(filename, text):
    return types.File(filename, code(Context(filename, text)))
