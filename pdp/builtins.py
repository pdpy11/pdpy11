import struct

from .containers import CaseInsensitiveDict
from .deferred import SizedDeferred, Deferred
from .insns import instructions
from .types import Register, AddressingModes
from . import reports


builtins = CaseInsensitiveDict(instructions)


class RawMetacommand:
    def __init__(self, fn):
        self.fn = fn
        self.name = "." + fn.__name__


    def substitute(self, insn):
        ok = True
        for operand in insn.operands:
            if isinstance(operand, AddressingModes.Immediate):
                what = "immediate value"
                reports.error(
                    (operand.ctx_start, operand.ctx_end, f"Unexpected immediate value in '{self.name}' metacommand.\nYou wrote '{operand}', you probably \x1b[3mmeant\x1b[23m '{operand.value}', proceeding under that assumption"),
                    (insn.name.ctx_start, insn.name.ctx_end, "Metacommand started here")
                )
                operand.addr = operand.value  # hotfix
            elif not isinstance(operand, AddressingModes.Relative):
                what = {
                    AddressingModes.Register: "register",
                    AddressingModes.RegisterDeferred: "deferred addressing mode",
                    AddressingModes.Autoincrement: "autoincrement addressing mode",
                    AddressingModes.AutoincrementDeferred: "autoincrement deferred addressing mode",
                    AddressingModes.Autodecrement: "autodecrement addressing mode",
                    AddressingModes.AutodecrementDeferred: "autodecrement deferred addressing mode",
                    AddressingModes.IndexDeferred: "index deferred addressing mode",
                    AddressingModes.Absolute: "absolute address",
                    AddressingModes.RelativeDeferred: "relative deferred addressing mode",
                    AddressingModes.Index: "index addressing mode"
                }[type(operand)]
                if isinstance(operand, Register):
                    what = "register"
                else:
                    assert False
                reports.error(
                    (operand.ctx_start, operand.ctx_end, f"Unexpected {what} in '{self.name}' metacommand"),
                    (insn.name.ctx_start, insn.name.ctx_end, "Metacommand started here")
                )
                ok = False

        if not ok:
            return None

        # Unfold operands that were parsed as relative addressing mode
        return self.fn(insn, [operand.addr for operand in insn.operands])


def raw_metacommand(fn):
    name = "." + fn.__name__
    builtins[name] = RawMetacommand(fn)


@raw_metacommand
def byte(_, operands):
    def encode_i8(operand):
        value = operand.get()
        if not isinstance(value, int):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.byte' metacommand takes an integer or a list of integers, {type(value).__name__} given")
            )
            return b""
        assert -2 ** 8 < value < 2 ** 8
        value %= 2 ** 8
        return struct.pack("<B", value)
    return SizedDeferred(len(operands), lambda: b"".join(encode_i8(operand) for operand in operands))


@raw_metacommand
def word(_, operands):
    def encode_i16(operand):
        value = operand.get()
        if not isinstance(value, int):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.word' metacommand takes an integer or a list of integers, {type(value).__name__} given")
            )
            return b""
        assert -2 ** 16 < value < 2 ** 16
        value %= 2 ** 16
        return struct.pack("<H", value)
    return SizedDeferred(2 * len(operands), lambda: b"".join(encode_i16(operand) for operand in operands))


@raw_metacommand
def dword(_, operands):
    def encode_i32(operand):
        value = operand.get()
        if not isinstance(value, int):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.dword' metacommand takes an integer or a list of integers, {type(value).__name__} given")
            )
            return b""
        assert -2 ** 32 < value < 2 ** 32
        value %= 2 ** 32
        return struct.pack("<H", value >> 16) + struct.pack("<H", value & 0xffff)
    return SizedDeferred(4 * len(operands), lambda: b"".join(encode_i32(operand) for operand in operands))


# pylint: disable=redefined-builtin
@raw_metacommand
def ascii(insn, operands):
    if len(operands) != 1:
        reports.error(
            (insn.ctx_start, insn.ctx_end, f"'.ascii' metacommand takes exactly 1 operand, {len(operands)} given")
        )
        return None
    operand = operands[0]
    def fn():
        value = operand.get()
        if not isinstance(value, str):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.ascii' metacommand takes a string, {type(value).__name__} given")
            )
            return b""
        return value.encode("windows-1251")
    return Deferred(fn)


@raw_metacommand
def asciz(insn, operands):
    if len(operands) != 1:
        reports.error(
            (insn.ctx_start, insn.ctx_end, f"'.asciz' metacommand takes exactly 1 operand, {len(operands)} given")
        )
        return None
    operand = operands[0]
    def fn():
        value = operand.get()
        if not isinstance(value, str):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.asciz' metacommand takes a string, {type(value).__name__} given")
            )
            return b""
        return value.encode("windows-1251") + b"\x00"
    return Deferred(fn)


@raw_metacommand
def blkb(insn, operands):
    if len(operands) != 1:
        reports.error(
            (insn.ctx_start, insn.ctx_end, f"'.blkb' metacommand takes exactly 1 operand, {len(operands)} given")
        )
        return None
    operand = operands[0]
    def fn():
        value = operand.get()
        if not isinstance(value, int):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.blkb' metacommand takes a string, {type(value).__name__} given")
            )
            return b""
        return b"\x00" * value
    return Deferred(fn)


@raw_metacommand
def blkw(insn, operands):
    if len(operands) != 1:
        reports.error(
            (insn.ctx_start, insn.ctx_end, f"'.blkw' metacommand takes exactly 1 operand, {len(operands)} given")
        )
        return None
    operand = operands[0]
    def fn():
        value = operand.get()
        if not isinstance(value, int):
            reports.error(
                (operand.ctx_start, operand.ctx_end, f"'.blkw' metacommand takes a string, {type(value).__name__} given")
            )
            return b""
        return b"\x00" * (2 * value)
    return Deferred(fn)


@raw_metacommand
def even(insn, operands):
    if len(operands) > 0:
        reports.error(
            (insn.ctx_start, insn.ctx_end, ".even metacommand does not take operands")
        )
    def fn():
        return b"\x00" if insn.emit_address % 2 == 1 else b""
    return Deferred(fn)
