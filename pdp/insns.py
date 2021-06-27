import struct

from .architecture import instruction_opcodes
from .builtins import get_as_int
from .containers import CaseInsensitiveDict
from .deferred import Deferred, SizedDeferred, BaseDeferred, wait
from .types import Token, Symbol, ParenthesizedExpression, Number
from . import operators
from . import reports



class RegisterOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char

    def encode(self, operand, state):
        if register := try_register_from_symbol(operand):
            return register.idx, b""
        else:
            insn = state["insn"]
            idx = {"s": "first", "d": "second"}[self.pattern_char]
            reports.error(
                (insn.ctx_start, insn.ctx_end, f"'{insn.name.name}' command accepts a register as the {idx} argument"),
                (operand.ctx_start, operand.ctx_end, "...but this value does not look like a register")
            )
            raise reports.RecoverableError("Register expected, expression passed")


class RegisterModeOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char

    def encode(self, operand, state):
        # Good luck debugging this
        # pylint: disable=isinstance-second-argument-not-valid-type
        if register := try_register_from_symbol(operand):
            mode = AddressingModes.Register(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.expr)):
            mode = AddressingModes.RegisterDeferred(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, operators.postadd) and isinstance(operand.operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.operand.expr)):
            mode = AddressingModes.Autoincrement(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.postadd) and isinstance(operand.operand.operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.operand.operand.expr)):
            mode = AddressingModes.AutoincrementDeferred(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, operators.neg) and isinstance(operand.operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.operand.expr)):
            mode = AddressingModes.Autodecrement(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.neg) and isinstance(operand.operand.operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.operand.operand.expr)):
            mode = AddressingModes.AutodecrementDeferred(operand.ctx_start, operand.ctx_end, register)
        elif isinstance(operand, operators.call) and (register := try_register_from_symbol(operand.operand)):
            mode = AddressingModes.Index(operand.ctx_start, operand.ctx_end, register, operand.callee)
        elif isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.call) and (register := try_register_from_symbol(operand.operand.operand)):
            mode = AddressingModes.IndexDeferred(operand.ctx_start, operand.ctx_end, register, operand.operand.callee)
        elif isinstance(operand, operators.deferred) and isinstance(operand.operand, ParenthesizedExpression) and (register := try_register_from_symbol(operand.operand.expr)):
            reports.warning(
                (operand.ctx_start, operand.ctx_end, f"PDP-11 doesn't have @({register}) mode. This expression is parsed as @0({register}), which does what you probably expect.\nHowever, this is in fact index deferred addressing with an implicit zero offset.\nYou might want to insert a zero for explicitness.")
            )
            mode = AddressingModes.IndexDeferred(operand.ctx_start, operand.ctx_end, register, Number(None, None, "0"))
        elif isinstance(operand, operators.immediate):
            mode = AddressingModes.Immediate(operand.ctx_start, operand.ctx_end, operand.operand)
        elif isinstance(operand, operators.deferred) and isinstance(operand.operand, operators.immediate):
            mode = AddressingModes.Absolute(operand.ctx_start, operand.ctx_end, operand.operand.operand)
        elif isinstance(operand, operators.deferred):
            mode = AddressingModes.RelativeDeferred(operand.ctx_start, operand.ctx_end, operand.operand)
        else:
            mode = AddressingModes.Relative(operand.ctx_start, operand.ctx_end, operand)

        return mode.get_mode(), mode.encode_inline(state)


class OffsetOperandStub:
    def __init__(self, pattern_char, bitness, unsigned):
        self.pattern_char = pattern_char
        self.bitness = bitness
        self.unsigned = unsigned


    def encode(self, operand, state):
        insn = state["insn"]

        if isinstance(operand, Number) and operand.representation[-1] != ".":
            operand = Symbol(operand.ctx_start, operand.ctx_end, operand.representation)
        elif "(" not in repr(operand):
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
                elif isinstance(token, ParenthesizedExpression):
                    token.expr = fixup_label(token.expr)
                elif isinstance(token, Number) and token.representation[-1] != ".":
                    if fixup_active:
                        reports.warning(
                            (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes an offset."),
                            (operand.ctx_start, operand.ctx_end, "It's operand is a complex expression."),
                            (token.ctx_start, token.ctx_end, f"Thus, for compatibility, the first number is treated as a local label.\nFor example, '1 + 2' is parsed as 'address of local label 1 plus two'.\nThis may be unintended, so please state your intent explicitly:\n- if you meant numbers to be numbers, add parentheses around the operand: '({operand})', and\n- if you wanted '{token}' to be a label, add a colon after it: '{token}:'.")
                        )
                        fixup_active = False
                        return Symbol(token.ctx_start, token.ctx_end, token.representation)
                elif isinstance(token, Symbol):
                    fixup_active = False
                return token
            fixup_label(operand)

        def fn():
            offset = wait(operand.resolve(state) - state["rel_address"])
            error = False
            if self.unsigned and offset > 0:
                reports.error(
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump backwards"),
                    (operand.ctx_start, operand.ctx_end, f"...but this offset is positive (exactly {offset})")
                )
                error = True
            min_offset = -2 ** (self.bitness + self.unsigned) + 2 * self.unsigned
            max_offset = 0 if self.unsigned else 2 ** self.bitness - 2
            if not min_offset <= offset <= max_offset:
                reports.error(
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' can only jump from {min_offset} to {max_offset} (inclusively)"),
                    (operand.ctx_start, operand.ctx_end, f"...but this offset is out of bounds ({offset})")
                )
                error = True
            if offset % 2 == 1:
                reports.error(
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
    def __init__(self, pattern_char, bitness, unsigned):
        self.pattern_char = pattern_char
        self.bitness = bitness
        self.unsigned = unsigned


    def encode(self, operand, state):
        insn = state["insn"]

        def fn():
            value = wait(operand.resolve(state))
            error = False
            if self.unsigned and value < 0:
                reports.error(
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes a non-negative immediate operand"),
                    (operand.ctx_start, operand.ctx_end, f"...but this value is negative (exactly {value})")
                )
                error = True
            min_value = 0 if self.unsigned else -2 ** self.bitness
            max_value = 2 ** self.bitness - 1
            if not min_value <= value <= max_value:
                reports.error(
                    (insn.name.ctx_start, insn.name.ctx_end, f"Instruction '{insn.name.name}' takes an immediate operand from {min_value} to {max_value} (inclusively)"),
                    (operand.ctx_start, operand.ctx_end, f"...but this value is out of bounds ({value})")
                )
                error = True
            if error:
                return 0
            return value % (2 ** self.bitness)
        return Deferred[int](fn), b""


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

class Register(Token):
    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name
        self.idx = REGISTER_NAMES[name.lower()]

    def __repr__(self):
        return f"{self.name}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name


class SimpleAddressingMode(Token):
    mode_code: int
    reg: Register

    # pylint: disable=arguments-differ
    def init(self, reg: Register):
        self.reg: Register = reg

    def get_mode(self):
        return (self.mode_code << 3) | self.reg.idx

    # pylint: disable=unused-argument
    def encode_inline(self, state):
        return b""


class AddressingModes:
    class Register(SimpleAddressingMode):
        mode_code = 0

        def __repr__(self):
            return repr(self.reg)

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class RegisterDeferred(SimpleAddressingMode):
        mode_code = 1

        def __repr__(self):
            return f"({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Autoincrement(SimpleAddressingMode):
        mode_code = 2

        def __repr__(self):
            return f"({self.reg})+"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class AutoincrementDeferred(SimpleAddressingMode):
        mode_code = 3

        def __repr__(self):
            return f"@({self.reg})+"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Autodecrement(SimpleAddressingMode):
        mode_code = 4

        def __repr__(self):
            return f"-({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class AutodecrementDeferred(SimpleAddressingMode):
        mode_code = 5

        def __repr__(self):
            return f"@-({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Index(SimpleAddressingMode):
        mode_code = 6

        # pylint: disable=arguments-differ
        def init(self, reg: Register, index):
            super().init(reg)
            self.index = index

        def __repr__(self):
            return f"{self.index}({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and (self.reg, self.index) == (rhs.reg, rhs.index)

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an index", self, self.index, 16, False)))


    class IndexDeferred(SimpleAddressingMode):
        mode_code = 7

        # pylint: disable=arguments-differ
        def init(self, reg: Register, index):
            super().init(reg)
            self.index = index

        def __repr__(self):
            return f"@{self.index}({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and (self.reg, self.index) == (rhs.reg, rhs.index)

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an index", self, self.index, 16, False)))


    class Immediate(Token):
        # pylint: disable=arguments-differ
        def init(self, value):
            self.value = value

        def __repr__(self):
            return f"#{self.value}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.value == rhs.value

        def get_mode(self):
            return 0o27

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an immediate value", self, self.value, 16, False)))


    class Absolute(Token):
        # pylint: disable=arguments-differ
        def init(self, addr):
            self.addr = addr

        def __repr__(self):
            return f"@#{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def get_mode(self):
            return 0o37

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", get_as_int(state, "an absolute address", self, self.addr, 16, False)))


    class Relative(Token):
        # pylint: disable=arguments-differ
        def init(self, addr: Token):
            self.addr: Token = addr

        def __repr__(self):
            return f"{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def get_mode(self):
            return 0o67

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", wait(self.addr.resolve(state) - state["rel_address"] - 2) % (2 ** 16)))


    class RelativeDeferred(Token):
        # pylint: disable=arguments-differ
        def init(self, addr):
            self.addr = addr

        def __repr__(self):
            return f"@{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def get_mode(self):
            return 0o77

        def encode_inline(self, state):
            return SizedDeferred[bytes](2, lambda: struct.pack("<H", wait(self.addr.resolve(state) - state["rel_address"] - 2) % (2 ** 16)))


def try_register_from_symbol(operand):
    if isinstance(operand, Symbol) and operand.name.lower() in REGISTER_NAMES:
        return Register(operand.ctx_start, operand.ctx_end, operand.name)
    else:
        return None


class Instruction:
    def __init__(self, name, opcode_pattern, src_operand, dst_operand):
        self.name = name
        self.opcode_pattern = opcode_pattern
        self.src_operand = src_operand
        self.dst_operand = dst_operand


    def compile(self, state, compiler, insn):
        state = {**state, "insn": insn, "compiler": compiler}

        operand_stubs = [op for op in (self.src_operand, self.dst_operand) if op is not None]

        if len(insn.operands) < len(operand_stubs):
            reports.error(
                (insn.ctx_start, insn.ctx_end, f"Too few operands for '{self.name}' instruction: {len(operand_stubs)} expected, {len(insn.operands)} given")
            )
            return None
        elif len(insn.operands) > len(operand_stubs):
            reports.error(
                (insn.ctx_start, insn.ctx_end, f"Too many operands for '{self.name}' instruction: {len(operand_stubs)} expected, {len(insn.operands)} given")
            )
            return None


        replacements = []
        operands_encoding = b""

        for stub, operand_expr in zip(operand_stubs, insn.operands):
            opcode_inline_value, operand_encoding = stub.encode(operand_expr, {**state, "rel_address": state["emit_address"] + 2 + len(operands_encoding)})
            replacements.append((stub.pattern_char, opcode_inline_value))
            operands_encoding += operand_encoding

        def get_opcode():
            opcode_pattern = self.opcode_pattern
            for pattern_char, opcode_inline_value in replacements:
                value = wait(opcode_inline_value)
                splitted = opcode_pattern.split(pattern_char)
                opcode_pattern = "".join(splitted[i] + str((value >> (len(splitted) - 2 - i)) & 1) for i in range(0, len(splitted) - 1)) + splitted[-1]
            assert opcode_pattern.isdigit()
            return struct.pack("<H", int(opcode_pattern, 2))

        if any(isinstance(opcode_inline_value, BaseDeferred) for _, opcode_inline_value in replacements):
            return SizedDeferred[bytes](2, get_opcode) + operands_encoding
        else:
            return get_opcode() + operands_encoding




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
        assert len(opcode_pattern) == 16

        # Detect operand types
        src_operand = None
        dst_operand = None

        cnt_s = opcode_pattern.count("s")
        if cnt_s > 0:
            assert cnt_s in (3, 6)
            if cnt_s == 6:
                src_operand = RegisterModeOperandStub("s")
            else:
                src_operand = RegisterOperandStub("s")

        cnt_d = opcode_pattern.count("d")
        if cnt_d > 0:
            assert cnt_d in (3, 6)
            if cnt_d == 6:
                dst_operand = RegisterModeOperandStub("d")
            else:
                dst_operand = RegisterOperandStub("d")

        if "o" in opcode_pattern or "O" in opcode_pattern:
            unsigned = "O" in opcode_pattern
            char = "O" if unsigned else "o"
            if src_operand is None:
                src_operand = OffsetOperandStub(char, opcode_pattern.count(char), unsigned)
            else:
                assert dst_operand is None
                dst_operand = OffsetOperandStub(char, opcode_pattern.count(char), unsigned)

        if "i" in opcode_pattern or "I" in opcode_pattern:
            assert "o" not in opcode_pattern and "O" not in opcode_pattern
            unsigned = "I" in opcode_pattern
            char = "I" if unsigned else "i"
            assert src_operand is None
            src_operand = ImmediateOperandStub(char, opcode_pattern.count(char), unsigned)

        instructions[insn_name] = Instruction(insn_name, opcode_pattern, src_operand, dst_operand)


init()
