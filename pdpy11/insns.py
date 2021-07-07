import struct

from .architecture import instruction_opcodes
from .builtins import get_as_int
from .containers import CaseInsensitiveDict
from .deferred import Deferred, SizedDeferred, wait
from .types import Symbol, ParenthesizedExpression, Number, InstructionPointer, Label
from . import operators
from . import reports


def try_accumulator_from_symbol(operand):
    if isinstance(operand, Symbol):
        name = operand.name.lower()
        if len(name) == 3 and "ac0" <= name <= "ac5":
            return int(name[2])
    return None


REGISTER_NAMES = {
    "r0": 0,
    "r1": 1,
    "r2": 2,
    "r3": 3,
    "r4": 4,
    "r5": 5,
    "r6": 6,
    "r7": 7,
    "sp": 6,
    "pc": 7
}

def try_register_from_symbol(operand):
    if isinstance(operand, Symbol) and operand.name.lower() in REGISTER_NAMES:
        return REGISTER_NAMES[operand.name.lower()]
    else:
        return None

def is_register(operand):
    return try_register_from_symbol(operand) is not None


class RegisterOperandStub:
    def __init__(self, pattern_char, bit_indexes):
        self.pattern_char = pattern_char
        self.bit_indexes = bit_indexes

    def encode(self, operand, state):
        register = try_register_from_symbol(operand)
        if register is not None:
            return register, b""

        insn = state["insn"]
        idx = {"s": "first", "d": "second"}[self.pattern_char]
        reports.error(
            "invalid-addressing",
            (insn.ctx_start, insn.ctx_end, f"Instruction '{insn.name.name}' accepts a register as the {idx} argument"),
            (operand.ctx_start, operand.ctx_end, "...but this value does not look like a register")
        )
        raise reports.RecoverableError("Register expected, expression passed")


class RegisterModeOperandStub:
    def __init__(self, pattern_char, bit_indexes):
        self.pattern_char = pattern_char
        self.bit_indexes = bit_indexes

    def encode(self, operand, state):
        # Hoisting. 'a+b(c)' is parsed as 'a+(b(c))', not as '(a+b)(c)'. This is
        # great for function calls, but terrible for index addressing. Hence
        # we're 'hoisting' registers up here.
        def hoist(token):
            if isinstance(token, operators.InfixOperator):
                token.rhs = hoist(token.rhs)
                if isinstance(token.rhs, operators.call) and is_register(token.rhs.operand):
                    register = token.rhs.operand
                    ctx_end = token.ctx_end
                    token.rhs = token.rhs.callee
                    token.ctx_end = token.rhs.ctx_end
                    return operators.call(token.ctx_start, ctx_end, token, register)
            elif isinstance(token, operators.PrefixOperator):
                token.operand = hoist(token.operand)
                if isinstance(token.operand, operators.call) and is_register(token.operand.operand):
                    register = token.operand.operand
                    ctx_end = token.ctx_end
                    token.operand = token.operand.callee
                    token.ctx_end = token.operand.ctx_end
                    return operators.call(token.ctx_start, ctx_end, token, register)
            return token
        operand = hoist(operand)

        # Good luck debugging this
        # pylint: disable=isinstance-second-argument-not-valid-type
        register = try_register_from_symbol(operand)
        if register is not None:
            # Register
            return register, b""

        if isinstance(operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.expr)
            if register is not None:
                # Register deferred
                return 0o10 | register, b""

        if isinstance(operand, operators.deferred):
            register = try_register_from_symbol(operand.operand)
            if register is not None:
                # Register deferred
                reports.warning(
                    "legacy-deferred",
                    (operand.ctx_start, operand.ctx_end, f"{operand!r} is a legacy way of spelling ({operand.operand!r}), please use the new syntax")
                )
                return 0o10 | register, b""

        if isinstance(operand, operators.postadd) and isinstance(operand.operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.operand.expr)
            if register is not None:
                # Autoincrement
                return 0o20 | register, b""

        if isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.postadd) and isinstance(operand.operand.operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.operand.operand.expr)
            if register is not None:
                # Autoincrement deferred
                return 0o30 | register, b""

        if isinstance(operand, operators.neg) and isinstance(operand.operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.operand.expr)
            if register is not None:
                # Autodecrement
                return 0o40 | register, b""

        if isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.neg) and isinstance(operand.operand.operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.operand.operand.expr)
            if register is not None:
                # Autodecrement deferred
                return 0o50 | register, b""

        # Yes, I am aware that the nesting is broken here, but that's thanks to
        # hoisting and that's the least hacky way I had come up with.
        if isinstance(operand, operators.call) and isinstance(operand.callee, operators.deferred):
            register = try_register_from_symbol(operand.operand)
            if register is not None:
                # Index deferred
                return 0o70 | register, SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an index", operand, operand.callee.operand, bitness=16, unsigned=False)))

        if isinstance(operand, operators.call):
            register = try_register_from_symbol(operand.operand)
            if register is not None:
                # Index
                return 0o60 | register, SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an index", operand, operand.callee, bitness=16, unsigned=False)))

        if isinstance(operand, operators.deferred) and isinstance(operand.operand, ParenthesizedExpression):
            register = try_register_from_symbol(operand.operand.expr)
            if register is not None:
                # Index deferred with implicit zero index
                reports.warning(
                    "implicit-index",
                    (operand.ctx_start, operand.ctx_end, f"PDP-11 doesn't have {operand!r} addressing mode.\nThis expression is parsed as @0{operand.operand!r}, which does what you probably expect.\nHowever, this is in fact index deferred addressing with an implicit zero offset.\nYou might want to insert a zero for clarity.")
                )
                return 0o70 | register, b"\x00\x00"

        if isinstance(operand, operators.immediate):
            # Immediate
            return 0o27, SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an immediate value", operand, operand.operand, bitness=16, unsigned=False)))

        if isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.immediate):
            # Absolute
            return 0o37, SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an absolute address", operand, operand.operand.operand, bitness=16, unsigned=False)))

        if isinstance(operand, operators.deferred):
            # Relative deferred
            return 0o77, SizedDeferred[bytes](2, lambda: struct.pack("<H", wait(operand.operand.resolve(state) - state["rel_address"] - 2) % (2 ** 16)))

        # Relative
        return 0o67, SizedDeferred[bytes](2, lambda: struct.pack("<H", wait(operand.resolve(state) - state["rel_address"] - 2) % (2 ** 16)))


class FP11RMOperandStub(RegisterModeOperandStub):
    def encode(self, operand, state):
        acc = try_accumulator_from_symbol(operand)
        if acc is not None:
            # FP11 accumulator
            return acc, b""

        register = try_register_from_symbol(operand)
        if register is not None:
            (reports.warning if register < 6 else reports.error)(
                "implicit-accumulator",
                (
                    operand.ctx_start, operand.ctx_end,
                    f"This FP11 instruction takes either an accumulator, or any CPU addressing mode except simple register for this operand.\n{operand!r} will be implicitly treated as ac{register} in this context -- please use the latter mnemonic for clarity."
                    + ("" if register < 6 else "\nMoreover, accumulator ac{register} does not exist, because only accumulators ac0 to ac5 exist.")
                )
            )
            return register, b""

        return super().encode(operand, state)


class OffsetOperandStub:
    def __init__(self, pattern_char, bit_indexes, unsigned):
        self.pattern_char = pattern_char
        self.bit_indexes = bit_indexes
        self.unsigned = unsigned


    def encode(self, operand, state):
        insn = state["insn"]

        if isinstance(operand, Number) and operand.representation[-1] != ".":
            operand = Symbol(operand.ctx_start, operand.ctx_end, operand.representation)
        elif "(" not in operand.text() and ":" not in operand.text():
            # TODO: the condition of this if being '"(" not in operand.text()'
            # may not work for multiline expressions, e.g.
            #   clr @#1 +  ; comment here (abacaba)
            #   b
            fixup_active = True
            def fixup_label(token):
                nonlocal fixup_active
                if isinstance(token, operators.InfixOperator):
                    token.lhs = fixup_label(token.lhs)
                    token.rhs = fixup_label(token.rhs)
                elif isinstance(token, (operators.PrefixOperator, operators.PostfixOperator)):
                    token.operand = fixup_label(token.operand)
                elif isinstance(token, operators.call):
                    token.callee = fixup_label(token.callee)
                    token.operand = fixup_label(token.operand)
                elif isinstance(token, Number) and token.representation[-1] != ".":
                    if fixup_active:
                        reports.warning(
                            "label-fixup",
                            (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes an offset."),
                            (operand.ctx_start, operand.ctx_end, "It's operand is a complex expression."),
                            (token.ctx_start, token.ctx_end, f"Thus, for compatibility, the first number is treated as a local label.\nFor example, '1 + 2' is parsed as 'address of local label 1 plus two'.\nThis may be unintended, so please state your intent explicitly:\n- if you meant numbers to be numbers, add parentheses around the operand: '({operand!r})', and\n- if you wanted '{token!r}' to be a label, add a colon after it: '{token!r}:'.")
                        )
                        fixup_active = False
                        return Symbol(token.ctx_start, token.ctx_end, token.representation)
                elif isinstance(token, (Symbol, InstructionPointer)):
                    fixup_active = False
                else:
                    assert False  # TODO: really?
                return token
            fixup_label(operand)

        def fn():
            offset = wait(operand.resolve(state) - state["rel_address"])
            error = False
            if self.unsigned and offset > 0:
                if isinstance(operand, Symbol) and isinstance(operand.locate_definition(state), Label):
                    definition = operand.locate_definition(state)
                    reports.error(
                        "branch-out-of-bounds",
                        (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump backwards"),
                        (definition.ctx_start, definition.ctx_end, "...but the destination is located further")
                    )
                else:
                    reports.error(
                        "branch-out-of-bounds",
                        (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump backwards"),
                        (operand.ctx_start, operand.ctx_end, f"...but the offset to the destination is positive (exactly {offset})")
                    )
                error = True
            else:
                bitness = len(self.bit_indexes)
                min_offset = -2 ** (bitness + self.unsigned) + 2 * self.unsigned
                max_offset = 0 if self.unsigned else 2 ** bitness - 2
                if not min_offset <= offset <= max_offset:
                    reports.error(
                        "branch-out-of-bounds",
                        (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump from {min_offset} to {max_offset} (inclusively)"),
                        (operand.ctx_start, operand.ctx_end, f"...but this offset is out of bounds ({offset})")
                    )
                    error = True
            if offset % 2 == 1:
                reports.error(
                    "odd-branch",
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump by an even offset"),
                    (operand.ctx_start, operand.ctx_end, f"...but this offset is odd ({offset}, in particular)")
                )
                error = True
            if error:
                return 0
            if self.unsigned:
                return -offset // 2
            else:
                return offset // 2
        return Deferred[int](fn), b""



class ImmediateOperandStub:
    def __init__(self, pattern_char, bit_indexes, unsigned):
        self.pattern_char = pattern_char
        self.bit_indexes = bit_indexes
        self.unsigned = unsigned


    def encode(self, operand, state):
        insn = state["insn"]

        if isinstance(operand, operators.immediate):  # pylint: disable=isinstance-second-argument-not-valid-type
            reports.warning(
                "excess-hash",
                (operand.ctx_start, operand.ctx_end, f"'{insn.name.name}' instruction takes an immediate value implicitly, a hash is unnecessary")
            )
            operand = operand.operand

        def fn():
            bitness = len(self.bit_indexes)
            value = wait(operand.resolve(state))
            if self.unsigned and value < 0:
                reports.error(
                    "value-out-of-bounds",
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes a non-negative immediate operand"),
                    (operand.ctx_start, operand.ctx_end, f"...but this value is negative (exactly {value})")
                )
                return 0
            else:
                min_value = 0 if self.unsigned else -2 ** bitness + 1
                max_value = 2 ** bitness - 1
                if not min_value <= value <= max_value:
                    reports.error(
                        "value-out-of-bounds",
                        (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes an immediate operand from {min_value} to {max_value} (inclusively)"),
                        (operand.ctx_start, operand.ctx_end, f"...but this value is out of bounds ({value})")
                    )
                    return 0
            return value % (2 ** bitness)
        return Deferred[int](fn), b""



class FP11AccumulatorOperandStub:
    def __init__(self, pattern_char, bit_indexes):
        self.pattern_char = pattern_char
        self.bit_indexes = bit_indexes

    def encode(self, operand, state):
        acc = try_accumulator_from_symbol(operand)
        if acc is None:
            insn = state["insn"]
            idx = {"S": "first", "D": "second"}[self.pattern_char]
            reports.error(
                "invalid-addressing",
                (insn.ctx_start, insn.ctx_end, f"'{insn.name.name}' FP11 instruction accepts an accumulator as the {idx} argument"),
                (operand.ctx_start, operand.ctx_end, "...but this value does not look like a accumulator.\nThe supported accumulator names are 'ac0' to 'ac5'.")
            )
            raise reports.RecoverableError("FP11 accumulator expected, expression passed")

        return acc, b""


class Instruction:
    def __init__(self, name, opcode_pattern, operands):
        self.name = name
        self.opcode_pattern = opcode_pattern
        self.operands = operands
        self.min_operands = len(operands)
        self.max_operands = len(operands)


    def compile_insn(self, state, insn):
        if len(insn.operands) < len(self.operands):
            reports.error(
                "wrong-operands",
                (insn.ctx_start, insn.ctx_end, f"Too few operands for '{self.name}' instruction: {len(self.operands)} expected, {len(insn.operands)} given")
            )
            return None
        elif len(insn.operands) > len(self.operands):
            reports.error(
                "wrong-operands",
                (insn.ctx_start, insn.ctx_end, f"Too many operands for '{self.name}' instruction: {len(self.operands)} expected, {len(insn.operands)} given")
            )
            return None


        replacements = []
        operands_encoding = b""

        for stub, operand_expr in zip(self.operands, insn.operands):
            opcode_inline_value, operand_encoding = stub.encode(operand_expr, {**state, "rel_address": state["emit_address"] + 2 + len(operands_encoding)})
            replacements.append((stub, opcode_inline_value))
            operands_encoding += operand_encoding

        indexes_of_char = {}
        for i, char in enumerate(self.opcode_pattern):
            if char not in indexes_of_char:
                indexes_of_char[char] = []
            indexes_of_char[char].append(i)

        def get_opcode():
            opcode_pattern = list(self.opcode_pattern)
            for stub, opcode_inline_value in replacements:
                value = wait(opcode_inline_value)
                for i, index in enumerate(stub.bit_indexes):
                    opcode_pattern[indexes_of_char[stub.pattern_char][index]] = str((value >> i) & 1)
            str_opcode_pattern = "".join(opcode_pattern)
            assert str_opcode_pattern.isdigit()

            return struct.pack("<H", int(str_opcode_pattern, 2))

        return SizedDeferred[bytes](2, get_opcode) + operands_encoding




instructions = CaseInsensitiveDict()


def init():
    for insn_name, oct_opcode_pattern in instruction_opcodes.items():
        # Convert 8-base opcode pattern to binary pattern
        is_binary = False
        opcode_pattern = ""
        for i, char in enumerate(oct_opcode_pattern):
            if char == "[":
                is_binary = True
            elif char == "]":
                is_binary = False
            elif not char.isdigit():
                opcode_pattern += char * (1 if is_binary else 3)
            else:
                if is_binary or i == 0:
                    opcode_pattern += char
                else:
                    opcode_pattern += bin(int(char, 8))[2:].rjust(3, "0")
        assert len(opcode_pattern) == 16, insn_name

        # Detect operand types
        operands = []

        cnt_s = opcode_pattern.count("s")
        if cnt_s == 0:
            pass
        elif cnt_s == 3:
            operands.append(RegisterOperandStub("s", [2, 1, 0]))
        elif cnt_s == 6:
            operands.append(RegisterModeOperandStub("s", [5, 4, 3, 2, 1, 0]))
        elif cnt_s == 12:
            operands.append(RegisterModeOperandStub("s", [5, 4, 3, 2, 1, 0]))
            operands.append(RegisterModeOperandStub("s", [11, 10, 9, 8, 7, 6]))
        else:
            assert False, insn_name  # pragma: no cover

        cnt_float_s = opcode_pattern.count("S")
        if cnt_float_s == 0:
            pass
        elif cnt_float_s == 2:
            operands.append(FP11AccumulatorOperandStub("S", [1, 0]))
        elif cnt_float_s == 6:
            operands.append(FP11RMOperandStub("S", [5, 4, 3, 2, 1, 0]))
        elif cnt_float_s == 8:
            operands.append(FP11RMOperandStub("S", [7, 6, 5, 4, 3, 2]))
            operands.append(FP11AccumulatorOperandStub("S", [1, 0]))
        else:
            assert False, insn_name  # pragma: no cover

        cnt_d = opcode_pattern.count("d")
        if cnt_d == 0:
            pass
        elif cnt_d == 3:
            operands.append(RegisterOperandStub("d", [2, 1, 0]))
        elif cnt_d == 6:
            operands.append(RegisterModeOperandStub("d", [5, 4, 3, 2, 1, 0]))
        else:
            assert False, insn_name  # pragma: no cover

        cnt_float_d = opcode_pattern.count("D")
        if cnt_float_d == 0:
            pass
        elif cnt_float_d == 2:
            operands.append(FP11AccumulatorOperandStub("D", [1, 0]))
        elif cnt_float_d == 6:
            operands.append(FP11RMOperandStub("D", [5, 4, 3, 2, 1, 0]))
        else:
            assert False, insn_name  # pragma: no cover

        if "o" in opcode_pattern or "O" in opcode_pattern:
            unsigned = "O" in opcode_pattern
            char = "O" if unsigned else "o"
            bitness = opcode_pattern.count(char)
            operand = OffsetOperandStub(char, list(range(bitness - 1, -1, -1)), unsigned)
            if cnt_d == 0:
                operands.append(operand)
            else:
                operands.insert(0, operand)

        if "i" in opcode_pattern or "I" in opcode_pattern:
            assert "o" not in opcode_pattern and "O" not in opcode_pattern, insn_name
            unsigned = "I" in opcode_pattern
            char = "I" if unsigned else "i"
            bitness = opcode_pattern.count(char)
            operand = ImmediateOperandStub(char, list(range(bitness - 1, -1, -1)), unsigned)
            operands.insert(0, operand)

        assert all(c in "01234567sSdDoOiI" for c in opcode_pattern), insn_name

        instructions[insn_name] = Instruction(insn_name, opcode_pattern, operands)


init()
