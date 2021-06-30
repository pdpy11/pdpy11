import re

from .context import Context
from . import operators
from . import reports
from . import types


class Goto(BaseException):
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, exc_tb):
        return exc_type is Goto
goto = Goto()


COMMON_BUILTIN_INSTRUCTION_NAMES = {
    "mov", "movb", "cmp", "cmpb", "bit", "bitb", "bic", "bicb", "bis", "bisb",
    "add", "sub", "mul", "div", "ash", "ashc", "xor", "jmp", "swab", "clr",
    "clrb", "com", "comb", "inc", "incb", "dec", "decb", "neg", "negb", "adc",
    "adcb", "sbc", "sbcb", "tst", "tstb", "ror", "rorb", "rol", "rolb", "asr",
    "asrb", "asl", "aslb", "mtps", "mfpi", "mfpd", "mtpi", "mtpd", "sxt",
    "mfps", "br", "bne", "beq", "bge", "blt", "bgt", "ble", "bpl", "bmi", "bhi",
    "blos", "bvc", "bvs", "bcc", "bhis", "bcs", "blo", "sob", "jsr", "rts",
    "emt", "trap", "rti", "bpt", "iot", "rtt", "halt", "wait", "reset", "cln",
    "clz", "clv", "clc", "clnz", "clnv", "clnc", "clzv", "clzc", "clvc",
    "clnzv", "clnzc", "clnvc", "clzvc", "ccc", "sen", "sez", "sev", "sec",
    "senz", "senv", "senc", "sezv", "sezc", "sevc", "senzv", "senzc", "senvc",
    "sezvc", "scc", "spl"
}

UNCOMMON_BUILTIN_INSTRUCTION_NAMES = {
    "ret": "'ret' is a classic alias for 'rts sp'",
    "return": "'return' is a compatibility alias for 'ret'",
    "fadd": "'fadd' is a floating-point addition instruction",
    "fsub": "'fsub' is a floating-point subtraction instruction",
    "fmul": "'fmul' is a floating-point multiplication instruction",
    "fdiv": "'fdiv' is a floating-point division instruction",
    "call": "'call X' is a classic alias for 'jsr sp, X'"
}

REGISTER_NAMES = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc")


class Parser:
    def __init__(self, fn):
        self.fn = fn


    @classmethod
    def either(cls, parsers):
        def fn(ctx):
            for parser in parsers:
                if (result := parser(ctx, maybe=True)) is not None:
                    return result
            raise reports.RecoverableError("Failed to match either of the alternatives")
        return cls(fn)


    def __or__(self, rhs):
        assert isinstance(rhs, Parser)
        def fn(ctx):
            if (result := self(ctx, maybe=True)) is not None:
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
                    # unreachable
                    assert False  # pragma: no cover


    @classmethod
    def regex(cls, regex, skip_whitespace_before=True):
        regex = re.compile(regex)
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
    def literal(cls, literal, skip_whitespace_before=True):
        def fn(ctx):
            if skip_whitespace_before:
                ctx.skip_whitespace()
            if ctx.code[ctx.pos:ctx.pos + len(literal)] == literal:
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
opening_bracket = Parser.literal("{")
closing_bracket = Parser.literal("}")
plus = Parser.literal("+")
minus = Parser.literal("-")
colon = Parser.literal(":")
at_sign = Parser.literal("@")
hash_sign = Parser.literal("#")
equals_sign = Parser.literal("=")
single_quote = Parser.literal("'")
string_quote = Parser.literal("\"")
character = Parser.regex(r"[\s\S]", skip_whitespace_before=False)
string_backslash = Parser.literal("\\", skip_whitespace_before=False)


local_symbol_literal = Parser.regex(r"\d[a-zA-Z_0-9$]*")
symbol_literal = Parser.regex(r"[a-zA-Z_$][a-zA-Z_0-9$]*")
instruction_name = Parser.regex(r"\.?[a-zA-Z_][a-zA-Z_0-9]*")


@Parser
def number(ctx):
    negative = minus(ctx, maybe=True)
    sign = -1 if negative else 1
    sign_str = "-" if negative else ""

    ctx.skip_whitespace()
    ctx_start = ctx.save()

    first_digit = Parser.regex(r"\d")(ctx)

    boundary = r"(?![$_])\b"

    if first_digit == "0":
        if Parser.regex(r"[xX]", skip_whitespace_before=False)(ctx, maybe=True):
            # Hexadecimal number
            num = Parser.regex(rf"[0-9a-fA-F]+{boundary}", skip_whitespace_before=False)(ctx, report=(
                reports.critical,
                "invalid-number",
                (ctx_start, ctx, "A hexadecimal number was expected after '0x'")
            ))
            return types.Number(ctx_start, ctx, f"{sign_str}0x{num}", int(num, 16) * sign)
        elif Parser.regex(r"[oO]", skip_whitespace_before=False)(ctx, maybe=True):
            # Octal number
            num = Parser.regex(rf"[0-7]+{boundary}", skip_whitespace_before=False)(ctx, report=(
                reports.critical,
                "invalid-number",
                (ctx_start, ctx, "An octal number was expected after '0o'")
            ))
            return types.Number(ctx_start, ctx, f"{sign_str}0o{num}", int(num, 8) * sign)
        elif Parser.regex(r"[bB]", skip_whitespace_before=False)(ctx, maybe=True):
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


@Parser
def label(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    name = Parser.regex(r"([a-zA-Z_0-9$]+)\s*:")(ctx)
    name = name[:-1].strip()

    if name.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a label definition.\nPlease consider changing the label not to look like an instruction")
        )
    elif name.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a label definition.\nPlease consider changing the label not to look like an instruction.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[name.lower()])
        )
    elif name.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "Label name clashes with a register.\nYou won't be able to access this label because every usage would be parsed as a register.")
        )

    return types.Label(ctx_start, ctx, name)


@Parser
def assignment(ctx):
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

    if symbol.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a constant definition.\nPlease consider changing the constant name not to look like an instruction")
        )
    elif symbol.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a constant definition.\nPlease consider changing the constant name not to look like an instruction.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[symbol.lower()])
        )
    elif symbol.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx_after_symbol, f"Symbol name clashes with a register.\nYou won't be able to access this symbol because every usage would be parsed as a register.\nMaybe you are unfamiliar with assembly and wanted to say 'mov #{value!r}, {symbol}'? " + reports.terminal_link("Read an intro on PDP-11 assembly.", "https://pdpy.github.io/intro"))
        )

    return types.Assignment(ctx_start, ctx, types.Symbol(ctx_start, ctx_after_symbol, symbol), value)


@Parser
def symbol_expression(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx)
    if symbol.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as an operand.\nCheck for a missing newline or an excess comma before it.")
        )
    elif symbol.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as an operand.\nCheck for a missing newline or an excess comma before it.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[symbol.lower()])
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
        num = Parser.regex(r"[0-9a-fA-F]{2}")(ctx, report=(
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
def character_string(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    single_quote(ctx)

    if ctx.pos == len(ctx.code):
        reports.critical(
            "unterminated-string",
            (ctx_start, ctx, "Unterminated string literal")
        )

    value = ""
    if ctx.code[ctx.pos] != "'":
        value += string_char(ctx)

    if ctx.pos < len(ctx.code) and ctx.code[ctx.pos] == "'":
        single_quote(ctx)
        reports.error(
            "invalid-character",
            (ctx_start, ctx, "Single quotation mark denotes not a string, but a character.\nUnlike C, a character must not be terminated by a single quotation mark.\nFor example, 'a should be used instead of 'a'. Please remove the second quotation mark.")
        )

    return types.String(ctx_start, ctx, "'", value)


@Parser
def string(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    quotation_sign = string_quote(ctx)

    value = ""
    while ctx.pos < len(ctx.code) and ctx.code[ctx.pos] != quotation_sign:
        value += string_char(ctx)

    if ctx.pos == len(ctx.code):
        reports.critical(
            "unterminated-string",
            (ctx_start, ctx, "Unterminated string literal")
        )

    ctx.pos += 1
    return types.String(ctx_start, ctx, quotation_sign, value)


@Parser
def instruction_pointer(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    Parser.regex(r"\.(?![a-zA-Z_0-9])")(ctx)
    return types.InstructionPointer(ctx_start, ctx)

expression_literal = symbol_expression | number | local_symbol_expression | character_string | string | instruction_pointer

infix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.InfixOperator]])
prefix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PrefixOperator]])
postfix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PostfixOperator]])


@Parser
def expression_literal_rec(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    if opening_parenthesis(ctx, maybe=True, lookahead=True):
        value = None
    else:
        value = expression_literal(ctx)

    while opening_parenthesis(ctx, maybe=True):
        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()

        expr = expression(ctx, report=(
            reports.critical,
            "invalid-expression",
            (ctx, ctx, "Could not parse an expression here"),
            (ctx_start, ctx_after_paren, "...as expected after an opening parenthesis here")
        ))

        ctx.skip_whitespace()

        closing_parenthesis(ctx, report=(
            reports.critical,
            "invalid-expression",
            (ctx, ctx, "This is not a operator, so a closing parenthesis is expected here"),
            (ctx_start, ctx_after_paren, "...to match an opening parenthesis here")
        ))

        if value is None:
            value = types.ParenthesizedExpression(ctx_start, ctx, expr)
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
    while (expr := expression_literal_rec(ctx, maybe=True)) is None:
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
def instruction(ctx):
    ctx_start = ctx.save()
    insn_name = instruction_name(ctx)
    if insn_name.lower() in REGISTER_NAMES:
        reports.warning(
            "suspicious-name",
            (ctx_start, ctx, "Instruction name suspiciously resembles a register.\nCheck for an excess newline or a missing comma before the register name")
        )
    ctx_state_after_name = ctx.save()

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
        if (newline | closing_bracket)(ctx, maybe=True, lookahead=True):
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
            raise goto

        name = (instruction_name + ~colon)(ctx, maybe=True, lookahead=True)
        if name in COMMON_BUILTIN_INSTRUCTION_NAMES or name in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
            ctx_new = ctx.save()
            ctx_new.skip_whitespace()
            ctx_before_insn = ctx_new.save()
            next_insn_name = instruction_name(ctx_new)
            if not (comma | newline | infix_operator | postfix_operator)(ctx_new, maybe=True, lookahead=True):
                reports.warning(
                    "missing-newline",
                    (ctx_start, ctx_state_after_name, "There is no newline after the name of this instruction, hence an operand must follow,"),
                    (ctx_before_insn, ctx_new, f"but it suspiciously resembles another instruction.\nYou probably \x1b[3mmeant\x1b[23m an instruction '{insn_name}' without operands followed by a '{next_insn_name}' instruction,\nand pdpy will compile this code as such, but this is against standards; please add a newline between instructions.")
                )
                raise goto

        first_operand = expression(ctx, maybe=True)

        if first_operand:
            if ctx.code[ctx_state_after_name.pos].strip() != "":
                reports.error(
                    "missing-whitespace",
                    (ctx_state_after_name, ctx, "Expected whitespace after instruction name. Proceeding under assumption that an operand follows.")
                )

            operands = [first_operand]

            ctx_before_comma = ctx.save()
            while comma(ctx, maybe=True):
                ctx_after_comma = ctx.save()
                ctx.skip_whitespace()
                oper = expression(ctx, report=(
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

    return types.Instruction(ctx_start, ctx, types.Symbol(ctx_start, ctx_state_after_name, insn_name), operands)


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

    return types.CodeBlock(ctx_start, ctx, insns)


def parse(filename, text):
    return types.File(filename, code(Context(filename, text)))
