import re

from .context import Context
from .types import *
from . import reports


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


class RecoverableError(Exception):
    pass


class Parser:
    def __init__(self, fn):
        self.fn = fn


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
            self(ctx, skip_whitespace_after=False)
            return rhs(ctx, skip_whitespace_after=False)
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


    def __call__(self, ctx, *, maybe=False, skip_whitespace_after=False, lookahead=False, error=None, **kwargs):
        if maybe or lookahead:
            old_ctx = ctx.save()
            try:
                result = self.fn(ctx, **kwargs)
                assert result is not None
            except RecoverableError:
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
            except RecoverableError:
                if error is None:
                    raise
                elif callable(error):
                    error()
                    return None
                else:
                    reports.emit_report(*error)
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
                raise RecoverableError(f"Failed to match regex at position {ctx.pos}")
            ctx.pos = match.end()
            return match.group()
        return Parser(fn)


newline = Parser.regex(r"\s*\n|\s*;[^\n]*", skip_whitespace_before=False)
comma = Parser.regex(r",")
opening_parenthesis = Parser.regex(r"\(")
closing_parenthesis = Parser.regex(r"\)")
opening_bracket = Parser.regex(r"{")
closing_bracket = Parser.regex(r"}")
plus = Parser.regex(r"\+")
minus = Parser.regex(r"-")
at_sign = Parser.regex(r"@")
hash_sign = Parser.regex(r"#")
equals_sign = Parser.regex(r"=")
quote = Parser.regex("[\"']")


symbol_literal = Parser.regex(r"[a-zA-Z_$][a-zA-Z_0-9$]*")
instruction_name = Parser.regex(r"\.?[a-zA-Z_][a-zA-Z_0-9]*")

register = Parser.regex(r"([rR][0-7]|[sS][pP]|[pP][cC])\b") >> Register
number = Parser.regex(r"-?\d+\.?") >> Number


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
    return Label(ctx_start, ctx, name)


@Parser
def assignment(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    symbol = symbol_literal(ctx, skip_whitespace_after=True)

    ctx_equals = ctx.save()
    equals_sign(ctx, skip_whitespace_after=False)
    ctx_after_equals = ctx.save()
    ctx.skip_whitespace()

    value = expression(ctx, skip_whitespace_after=False, error=(
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

    return Assignment(ctx_start, ctx, symbol, value)


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

    return Symbol(ctx_start, ctx, symbol)


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
    return String(ctx_start, ctx, value)


@Parser
def instruction_pointer(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()
    Parser.regex(r"\.(?![a-zA-Z_0-9])")(ctx, skip_whitespace_after=False)
    return InstructionPointer(ctx_start, ctx)

expression_literal = number | symbol_expression | string | instruction_pointer

operator = Parser.regex(r"[+\-*/%]|>>|<<")
OPERATORS = {
    ">>": {"precedence": 1, "associativity": "left"},
    "<<": {"precedence": 1, "associativity": "left"},
    "+": {"precedence": 2, "associativity": "left"},
    "-": {"precedence": 2, "associativity": "left"},
    "*": {"precedence": 3, "associativity": "left"},
    "/": {"precedence": 3, "associativity": "left"},
    "%": {"precedence": 3, "associativity": "left"}
}

@Parser
def expression_literal_rec(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()

    if opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()

        expr = expression(ctx, skip_whitespace_after=True, error=(
            reports.critical,
            (ctx, ctx, "Could not parse an expression here"),
            (ctx_start, ctx_after_paren, "...as expected after an opening parenthesis here")
        ))

        closing_parenthesis(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx, ctx, "Expected a closing parenthesis here"),
            (ctx_start, ctx_after_paren, "...to match an opening parenthesis here")
        ))

        return expr
    else:
        return expression_literal(ctx, skip_whitespace_after=False)

@Parser
def expression(ctx):
    ctx.skip_whitespace()
    expr = expression_literal_rec(ctx, skip_whitespace_after=True)

    stack = [expr]
    op_stack = []

    while True:
        ctx_op = ctx.save()
        cur_operator = operator(ctx, maybe=True, skip_whitespace_after=False)
        if not cur_operator:
            break
        ctx_op_end = ctx.save()

        expr = expression_literal_rec(ctx, skip_whitespace_after=True, error=(
            reports.critical,
            (ctx, ctx, "Could not parse an expression here"),
            (ctx_op, ctx_op_end, f"...as expected after operator '{cur_operator}'")
        ))

        while op_stack != [] and (OPERATORS[op_stack[-1]["operator"]]["precedence"] > OPERATORS[cur_operator]["precedence"] or (OPERATORS[op_stack[-1]["operator"]]["precedence"] == OPERATORS[cur_operator]["precedence"] and OPERATORS[cur_operator]["associativity"] == "left")):
            lhs, rhs = stack[-2], stack[-1]
            stack.pop()
            stack[-1] = Operator(op_stack[-1]["ctx_start"], op_stack[-1]["ctx_end"], lhs, rhs, op_stack[-1]["operator"])
            op_stack.pop()

        stack.append(expr)
        op_stack.append({"ctx_start": ctx_op, "ctx_end": ctx_op_end, "operator": cur_operator})

    while op_stack:
        lhs, rhs = stack[-2], stack[-1]
        stack.pop()
        stack[-1] = Operator(op_stack[-1]["ctx_start"], op_stack[-1]["ctx_end"], lhs, rhs, op_stack[-1]["operator"])
        op_stack.pop()

    return stack[-1]


@Parser
def operand(ctx):
    ctx.skip_whitespace()
    ctx_start = ctx.save()


    if opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()
        reg = register(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_after_paren, "An opening parenthesis '(' in an operand must be followed by a register..."),
            (ctx, "...yet the value here does not denote a register name")
        ))
        ctx_after_reg = ctx.save()
        ctx.skip_whitespace()
        closing_parenthesis(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_after_reg, "An opening parenthesis '(', followed by a register name in an operand must be followed by a closing parenthesis..."),
            (ctx, ctx, "...yet no parenthesis was matched here")
        ))
        if plus(ctx, maybe=True, skip_whitespace_after=False):
            return AddressingModes.Autoincrement(ctx_start, ctx, reg)
        else:
            return AddressingModes.RegisterDeferred(ctx_start, ctx, reg)

    elif Parser.regex(r"-\(")(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_paren = ctx.save()
        ctx.skip_whitespace()
        reg = register(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_after_paren, "A minus and an opening parenthesis '-(' in an operand must be followed by a register..."),
            (ctx, ctx, "...yet the value here does not denote a register name")
        ))
        ctx_after_reg = ctx.save()
        ctx.skip_whitespace()
        closing_parenthesis(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_after_reg, "A minus and an opening parenthesis '-(', followed by a register name in an operand must be followed by a closing parenthesis..."),
            (ctx, "...yet no parenthesis was matched here")
        ))
        return AddressingModes.Autodecrement(ctx_start, ctx, reg)

    elif at_sign(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_at = ctx.save()
        ctx.skip_whitespace()

        if opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
            ctx_after_paren = ctx.save()
            ctx.skip_whitespace()
            reg = register(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_paren, "An at sign and an opening parenthesis '@(' in an operand must be followed by a register..."),
                (ctx, ctx, "...yet the value here does not denote a register name")
            ))
            ctx_after_reg = ctx.save()
            ctx.skip_whitespace()
            closing_parenthesis(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_reg, "An at sign and an opening parenthesis '@(', followed by a register name in an operand must be followed by a closing parenthesis..."),
                (ctx, ctx, "...yet no parenthesis was matched here")
            ))
            if plus(ctx, maybe=True, skip_whitespace_after=False):
                return AddressingModes.AutoincrementDeferred(ctx_start, ctx, reg)
            else:
                return AddressingModes.IndexDeferred(ctx_start, ctx, reg, Number(None, None, "0"))

        elif Parser.regex(r"-\(")(ctx, maybe=True, skip_whitespace_after=False):
            ctx_after_paren = ctx.save()
            ctx.skip_whitespace()
            reg = register(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_paren, "An at sign, a minus and an opening parenthesis '@-(' in an operand must be followed by a register..."),
                (ctx, ctx, "...yet the value here does not denote a register name")
            ))
            ctx_after_reg = ctx.save()
            ctx.skip_whitespace()
            closing_parenthesis(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_reg, "An at sign, a minus and an opening parenthesis '@-(', followed by a register name in an operand must be followed by a closing parenthesis..."),
                (ctx, ctx, "...yet no parenthesis was matched here")
            ))
            return AddressingModes.AutodecrementDeferred(ctx_start, ctx, reg)

        elif hash_sign(ctx, maybe=True, skip_whitespace_after=False):
            ctx_after_hash = ctx.save()
            ctx.skip_whitespace()
            addr = expression(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_hash, "An at sign and a hash sign '@#' in an operand must be followed by an address (as in absolute addressing)"),
                (ctx, ctx, "...yet an expression was not be matched here")
            ))
            return AddressingModes.Absolute(ctx_start, ctx, addr)

        else:
            index = expression(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_at, "An at sign '@' in an operand must be followed by:\n- '(rn)' (as in deferred addressing), e.g. @(r0), or\n- '(rn)+' (as in autoincrement deferred addressing), e.g. @(r0)+, or\n- '-(rn)' (as in autodecrement deferred addressing), e.g. @-(r0), or\n- an index (as in index deferred addressing), e.g. @123(r0) or @(1+2)(r0), or\n- an address (as in relative deferred addressing), e.g. @123 or @(1+2), or\n- '#n' (as in absolute addressing), e.g. @#123 or @#(1+2)"),
                (ctx, ctx, "...yet none of that was matched here")
            ))
            if opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
                ctx_after_paren = ctx.save()
                ctx.skip_whitespace()
                reg = register(ctx, skip_whitespace_after=False, error=(
                    reports.critical,
                    (ctx_start, ctx_after_paren, "An at sign '@' followed by an expression and a parenthesis '(' in an operand must be followed by a register (as in index deferred addressing)..."),
                    (ctx, ctx, "...yet the value here does not denote a register name")
                ))
                ctx_after_reg = ctx.save()
                ctx.skip_whitespace()
                closing_parenthesis(ctx, skip_whitespace_after=False, error=(
                    reports.critical,
                    (ctx_start, ctx_after_reg, "An at sign '@' followed by an expression, a parenthesis '(' and a register name must be followed by a parenthesis ')'"),
                    (ctx, ctx, "...yet no parenthesis was matched here")
                ))
                return AddressingModes.IndexDeferred(ctx_start, ctx, reg, index)
            else:
                return AddressingModes.RelativeDeferred(ctx_start, ctx, index)

    elif hash_sign(ctx, maybe=True, skip_whitespace_after=False):
        ctx_after_hash = ctx.save()
        ctx.skip_whitespace()
        value = expression(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_after_hash, "A hash sign '#' in an operand must be followed by an expression as in immediate addressing, e.g. #123"),
            (ctx, ctx, "...yet no expression was matched here")
        ))
        return AddressingModes.Immediate(ctx_start, ctx, value)

    elif reg := register(ctx, maybe=True, skip_whitespace_after=False):
        return AddressingModes.Register(ctx_start, ctx, reg)

    else:
        index = expression(ctx, skip_whitespace_after=False)
        if opening_parenthesis(ctx, maybe=True, skip_whitespace_after=False):
            ctx_after_paren = ctx.save()
            ctx.skip_whitespace()
            reg = register(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_paren, "An expression and a parenthesis '(' in an operand must be followed by a register (as in index addressing)..."),
                (ctx, ctx, "...yet the value here does not denote a register name")
            ))
            ctx_after_reg = ctx.save()
            ctx.skip_whitespace()
            closing_parenthesis(ctx, skip_whitespace_after=False, error=(
                reports.critical,
                (ctx_start, ctx_after_reg, "An expression, a parenthesis '(' and a register name must be followed by a parenthesis ')'"),
                (ctx, ctx, "...yet no parenthesis was matched here")
            ))
            return AddressingModes.Index(ctx_start, ctx, reg, index)
        else:
            return AddressingModes.Relative(ctx_start, ctx, index)


@Parser
def instruction(ctx):
    ctx_start = ctx.save()
    insn_name = instruction_name(ctx, skip_whitespace_after=False)
    if insn_name.lower() in ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "sp", "pc"):
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

        first_operand = operand(ctx, maybe=True, skip_whitespace_after=False)
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
                oper = operand(ctx, skip_whitespace_after=False, error=(
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

    return Instruction(ctx_start, ctx, Symbol(ctx_start, ctx_state_after_name, insn_name), operands)


@Parser
def code(ctx, break_on_closing_bracket=False):
    ctx_start = ctx.save()

    insns = []

    while not ctx.eof():
        ctx.skip_whitespace()
        ctx_start = ctx.save()
        if break_on_closing_bracket and closing_bracket(ctx, maybe=True, skip_whitespace_after=False):
            break

        insn = (label | assignment | instruction)(ctx, skip_whitespace_after=False, error=(
            reports.critical,
            (ctx_start, ctx_start, "Could not parse instruction starting from here")
        ))
        insns.append(insn)

    return CodeBlock(ctx_start, ctx, insns)


def parse(filename, text):
    return File(filename, code(Context(filename, text), skip_whitespace_after=False))
