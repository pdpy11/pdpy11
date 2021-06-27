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
                if (result := parser(ctx, maybe=True, skip_whitespace_after=False)) is not None:
                    return result
            raise reports.RecoverableError("Failed to match either of the alternatives")
        return cls(fn)


    def __or__(self, rhs):
        assert isinstance(rhs, Parser)
        def fn(ctx):
            if (result := self(ctx, maybe=True, skip_whitespace_after=False)) is not None:
                return result
            return rhs(ctx, skip_whitespace_after=False)
        return Parser(fn)


    def __add__(self, rhs):
        assert isinstance(rhs, Parser)
        def fn(ctx):
            result = self(ctx, skip_whitespace_after=False)
            rhs(ctx, skip_whitespace_after=False)
            return result
        return Parser(fn)


    def __rshift__(self, rhs):
        def fn(ctx):
            if callable(rhs):
                ctx_start = ctx.save()
                ctx_start.skip_whitespace()
                result = self(ctx, skip_whitespace_after=False)
                return rhs(ctx_start, ctx, result)
            else:
                self(ctx, skip_whitespace_after=False)
                return rhs
        return Parser(fn)


    def __call__(self, ctx, *, maybe=False, skip_whitespace_after=False, lookahead=False, report=None, **kwargs):
        if maybe or lookahead:
            old_ctx = ctx.save()
            try:
                result = self.fn(ctx, **kwargs)
                assert result is not None
            except reports.RecoverableError:
                if maybe:
                    ctx.restore(old_ctx)
                    return None
                else:
                    raise
            else:
                if lookahead:
                    ctx.restore(old_ctx)
                elif skip_whitespace_after:
                    ctx.skip_whitespace()
                return result
        else:
            try:
                result = self.fn(ctx, **kwargs)
                assert result is not None
                return result
            except reports.RecoverableError:
                if report is None:
                    raise
                elif callable(report):
                    report()
                    return None
                else:
                    reports.emit_report(*report)
                    return None
            else:
                if skip_whitespace_after:
                    ctx.skip_whitespace()


    @classmethod
    def regex(cls, regex, skip_whitespace_before=True):
        if not isinstance(regex, re.Pattern):
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
comma = Parser.regex(r",")
opening_parenthesis = Parser.regex(r"\(")
closing_parenthesis = Parser.regex(r"\)")
opening_bracket = Parser.regex(r"{")
closing_bracket = Parser.regex(r"}")
plus = Parser.regex(r"\+")
minus = Parser.regex(r"-")
colon = Parser.regex(r":")
at_sign = Parser.regex(r"@")
hash_sign = Parser.regex(r"#")
equals_sign = Parser.regex(r"=")
quote = Parser.regex("[\"']")


local_symbol_literal = Parser.regex(r"[0-9][a-zA-Z_0-9$]*")
symbol_literal = Parser.regex(r"[a-zA-Z_$][a-zA-Z_0-9$]*")
instruction_name = Parser.regex(r"\.?[a-zA-Z_][a-zA-Z_0-9]*")

number = Parser.regex(r"-?\d+\.?") >> types.Number


@Parser
def label(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    name = Parser.regex(r"([a-zA-Z_0-9$]+)\s*:")(ctx)
    name = name[:-1].strip()

    if name.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a label definition.\nPlease consider changing the label not to look like an instruction")
        )
    elif name.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a label definition.\nPlease consider changing the label not to look like an instruction.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[name.lower()])
        )
    elif name.lower() in REGISTER_NAMES:
        reports.error(
            (ctx_start, ctx, "Label name clashes with a register.\nYou won't be able to access this label because every usage would be parsed as a register")
        )

    return types.Label(ctx_start, ctx, name)


@Parser
def assignment(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx, skip_whitespace_after=False)
    ctx_after_symbol = ctx.save()
    ctx.skip_whitespace()

    ctx_equals = ctx.save()
    equals_sign(ctx, skip_whitespace_after=False)
    ctx_after_equals = ctx.save()
    ctx.skip_whitespace()

    value = expression(ctx, skip_whitespace_after=False, report=(
        reports.critical,
        (ctx_equals, ctx_after_equals, "An equals sign '=' must be followed by an expression (as in assignment)"),
        (ctx, ctx, "...yet no expression was matched here")
    ))

    if symbol.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a constant definition.\nPlease consider changing the constant name not to look like an instruction")
        )
    elif symbol.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as a constant definition.\nPlease consider changing the constant name not to look like an instruction.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[symbol.lower()])
        )
    elif symbol.lower() in REGISTER_NAMES:
        reports.error(
            (ctx_start, ctx_after_symbol, f"Symbol name clashes with a register.\nYou won't be able to access this symbol because every usage would be parsed as a register.\nMaybe you are unfamiliar with assembly and wanted to say 'mov #{value.token_text()}, {symbol}'? " + reports.terminal_link("Read an intro on PDP-11 assembly.", "https://pdpy.github.io/intro"))
        )

    return types.Assignment(ctx_start, ctx, symbol, value)


@Parser
def symbol_expression(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx, skip_whitespace_after=False)
    if symbol.lower() in COMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as an operand.\nCheck for a missing newline or an excess comma before it")
        )
    elif symbol.lower() in UNCOMMON_BUILTIN_INSTRUCTION_NAMES:
        reports.warning(
            (ctx_start, ctx, "This symbol suspiciously resembles an instruction, but is parsed as an operand.\nCheck for a missing newline or an excess comma before it.\n" + UNCOMMON_BUILTIN_INSTRUCTION_NAMES[symbol.lower()])
        )

    colon(ctx, maybe=True, skip_whitespace_after=False)

    return types.Symbol(ctx_start, ctx, symbol)


@Parser
def local_symbol_expression(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    symbol = local_symbol_literal(ctx, skip_whitespace_after=False)
    colon(ctx, skip_whitespace_after=False)
    return types.Symbol(ctx_start, ctx, symbol)


string_char = (
    (Parser.regex(r"\\n", skip_whitespace_before=False) >> "\n")
    | (Parser.regex(r"\\r", skip_whitespace_before=False) >> "\r")
    | (Parser.regex(r"\\t", skip_whitespace_before=False) >> "\t")
    | (Parser.regex(r"\\\\", skip_whitespace_before=False) >> "\\")
    | (Parser.regex(r"\\\n", skip_whitespace_before=False) >> "")
    | Parser.regex(r".", skip_whitespace_before=False)
)


@Parser
def string(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    quotation_sign = quote(ctx, skip_whitespace_after=False)

    value = ""
    while ctx.pos < len(ctx.code) and ctx.code[ctx.pos] != quotation_sign:
        value += string_char(ctx, skip_whitespace_after=False)

    if ctx.pos == len(ctx.code):
        reports.critical(
            (ctx_start, ctx, "Unterminated string literal")
        )

    ctx.pos += 1
    return types.String(ctx_start, ctx, quotation_sign, value)


@Parser
def instruction_pointer(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    Parser.regex(r"\.(?![a-zA-Z_0-9])")(ctx, skip_whitespace_after=False)
    return types.InstructionPointer(ctx_start, ctx)

expression_literal = symbol_expression | local_symbol_expression | number | string | instruction_pointer

infix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.InfixOperator]])
prefix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PrefixOperator]])
postfix_operator = Parser.either([Parser.literal(op) for op in operators.operators[operators.PostfixOperator]])


@Parser
def expression_literal_rec(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    if opening_parenthesis(ctx, maybe=True, lookahead=True, skip_whitespace_after=False):
        value = None
    else:
        value = expression_literal(ctx, skip_whitespace_after=False)

    while opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()

        expr = expression(ctx, skip_whitespace_after=True, report=(
            reports.critical,
            (ctx, ctx, "Could not parse an expression here"),
            (ctx_start, ctx_after_paren, "...as expected after an opening parenthesis here")
        ))

        closing_parenthesis(ctx, skip_whitespace_after=False, report=(
            reports.critical,
            (ctx, ctx, "Expected a closing parenthesis here"),
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
    ctx_op = ctx.save()

    # Try to match a full expression before matching a prefix operator, so that
    # -1 is parsed as -1, not -(1)
    while (expr := expression_literal_rec(ctx, maybe=True, skip_whitespace_after=False)) is None:
        char = prefix_operator(ctx, skip_whitespace_after=False)
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
            postfix_operator(ctx, skip_whitespace_after=False)
            ctx_op_end = ctx.save()

            operator = operators.operators[operators.PostfixOperator][char]

            self_precedence = operator.precedence

            while op_stack and self_precedence > op_stack[-1]["operator"].precedence:
                pop_op_stack(ctx_prev)

            stack[-1] = operator(ctx_op, ctx_op_end, stack[-1])
            break
        else:
            # Must be an infix operator
            char = infix_operator(ctx, maybe=True, skip_whitespace_after=False)
            if not char:
                ctx.restore(ctx_prev)
                break

            ctx_op_end = ctx.save()

            operator = operators.operators[operators.InfixOperator][char]

            expr = expression_literal_rec(ctx, skip_whitespace_after=True, report=(
                reports.critical,
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
    insn_name = instruction_name(ctx, skip_whitespace_after=False)
    if insn_name.lower() in REGISTER_NAMES:
        reports.warning(
            (ctx_start, ctx, "Instruction name suspiciously resembles a register.\nCheck for an excess newline or a missing comma before the register name")
        )
    ctx_state_after_name = ctx.save()

    operands = []

    if comma(ctx, maybe=True, lookahead=True):
        ctx_before_comma = ctx.save()
        comma(ctx, skip_whitespace_after=False)
        reports.critical(
            (ctx_before_comma, ctx, "Unexpected comma right after instruction name; expected an operand"),
            (ctx_start, ctx_state_after_name, "Instruction started here")
        )

    with goto:
        if newline(ctx, maybe=True, skip_whitespace_after=False):
            # The recommended way to separate instructions is using newlines,
            # e.g.
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

        if closing_bracket(ctx, maybe=True, lookahead=True):
            raise goto

        if instruction_name(ctx, maybe=True, lookahead=True) in COMMON_BUILTIN_INSTRUCTION_NAMES:
            ctx_new = ctx.save()
            ctx_new.skip_whitespace()
            ctx_before_insn = ctx_new.save()
            next_insn_name = instruction_name(ctx_new, skip_whitespace_after=False)
            if not comma(ctx_new, maybe=True, lookahead=True):
                reports.warning(
                    (ctx_start, ctx_state_after_name, "There is no newline after the name of this instruction, hence an operand must follow,"),
                    (ctx_before_insn, ctx_new, f"but it suspiciously resembles another instruction.\nYou probably \x1b[3mmeant\x1b[23m an instruction '{insn_name}' without operands followed by a '{next_insn_name}' instruction,\nand pdpy will compile this code as such, but this is against standards; please add a newline between instructions.")
                )
            raise goto

        first_operand = expression(ctx, maybe=True, skip_whitespace_after=False)
        if first_operand:
            if ctx_state_after_name.pos < len(ctx.code) and ctx.code[ctx_state_after_name.pos].strip() != "":
                reports.error(
                    (ctx_state_after_name, ctx, "Expected whitespace after instruction name. Moving on on assumption that an operand follows")
                )

            operands = [first_operand]

            ctx_before_comma = ctx.save()
            while comma(ctx, maybe=True, skip_whitespace_after=False):
                ctx_after_comma = ctx.save()
                ctx.skip_whitespace()
                oper = expression(ctx, skip_whitespace_after=False, report=(
                    reports.critical,
                    (ctx_before_comma, ctx_after_comma, "Expected operand after comma in an instruction"),
                    (ctx_start, ctx_state_after_name, "(instruction started here)"),
                    (ctx, ctx, "This definitely does not look like an operand")
                ))
                operands.append(oper)
                ctx_before_comma = ctx.save()

            ctx_opening_bracket = ctx.save()
            if opening_bracket(ctx, maybe=True, skip_whitespace_after=False):
                oper = code(ctx, break_on_closing_bracket=True, skip_whitespace_after=False)
                oper.ctx = ctx_opening_bracket
                operands.append(oper)

            if ctx.pos < len(ctx.code) and ctx.code[ctx.pos].strip() != "":
                reports.error(
                    (ctx, ctx, "Expected whitespace after instruction. Proceeding as if a new instruction is starting")
                )
        else:
            if ctx_state_after_name.pos < len(ctx.code) and "\n" not in ctx.code[ctx_state_after_name.pos:ctx.pos]:
                ctx.skip_whitespace()
                reports.warning(
                    (ctx, ctx, "Could not parse an operand starting from here; assuming a new instruction.\nPlease add a newline here if an instruction was implied"),
                    (ctx_start, ctx_state_after_name, "The previous instruction started here")
                )

            if ctx_state_after_name.pos < len(ctx.code) and ctx.code[ctx_state_after_name.pos].strip() != "":
                reports.error(
                    (ctx_state_after_name, ctx, "Expected whitespace after instruction name. Proceeding under assumption that another instruction follows")
                )

    return types.Instruction(ctx_start, ctx, types.Symbol(ctx_start, ctx_state_after_name, insn_name), operands)


@Parser
def code(ctx, break_on_closing_bracket=False):
    ctx_start = ctx.save()

    insns = []

    while not ctx.eof():
        ctx.skip_whitespace()
        ctx_start = ctx.save()
        if break_on_closing_bracket and closing_bracket(ctx, maybe=True, skip_whitespace_after=False):
            break

        insn = (label | assignment | instruction)(ctx, skip_whitespace_after=False, report=(
            reports.critical,
            (ctx_start, ctx_start, "Could not parse instruction starting from here")
        ))
        insns.append(insn)

    return types.CodeBlock(ctx_start, ctx, insns)


def parse(filename, text):
    return types.File(filename, code(Context(filename, text), skip_whitespace_after=False))
