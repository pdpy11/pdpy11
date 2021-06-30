import inspect
import struct

from .containers import CaseInsensitiveDict
from .deferred import Deferred, SizedDeferred, wait, BaseDeferred
from .types import CodeBlock, String
from . import operators
from . import reports


def get_as_int(state, what, token, arg_token, bitness, unsigned, recommend_ascii=False):
    value = wait(arg_token.resolve(state))
    if isinstance(value, int):
        if unsigned and value < 0:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"An unsigned integer is expected as {what}, but {value} was passed")
            )
            raise reports.RecoverableError("A negative value was passed when an unsigned value was expected")
        if value <= -2 ** bitness:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"The value is too small: {value} does not fit in {bitness} bits")
            )
            raise reports.RecoverableError("Too negative value")
        if value >= 2 ** bitness:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"The value is too large: {value} does not fit in {bitness} bits")
            )
            raise reports.RecoverableError("Too large value")
        return value % (2 ** bitness)
    elif isinstance(value, str):
        if recommend_ascii:
            reports.warning(
                "use-ascii",
                (arg_token.ctx_start, arg_token.ctx_end, f"Passing a string to metacommand '{token.name.name}', which implicitly converts it\nto a number and then writes back as a series of bytes is not particularly graceful.\nConsider using '.ascii' metacommand instead.")
            )
        else:
            if isinstance(arg_token, String) and len(value) == 1 and arg_token.quote != "'":
                reports.warning(
                    "implicit-pack",
                    (arg_token.ctx_start, arg_token.ctx_end, f"A character that is used as {what} is implicitly converted to a number.\nConsider using a single quote ' as a cleaner solution, e.g. 'A instead of \"A\".")
                )
            elif not isinstance(arg_token, String) or (arg_token.quote != "'" and len(value) != 2):
                reports.warning(
                    "implicit-pack",
                    (arg_token.ctx_start, arg_token.ctx_end, f"A string is used as {what}, but a number was expected.\nTechnically, a short string can be encoded as an integer,\nbut this is asking for trouble if you didn't intend that.\nPlease state your intention explicitly by casting the string like this: 'pack(\"...\")'.\nNote that this is not the same as defining a string using '.ascii' elsewhere and then using its address.")
                )

        if value == "":
            reports.warning(
                "empty-pack",
                (arg_token.ctx_start, arg_token.ctx_end, "Encoding an empty string as integer may possibly be a bug" + (f".\nThis inserts {bitness // 8} null byte{'s' if bitness > 8 else ''} into the binary file." if recommend_ascii else ""))
            )
        value = value.encode("koi8-r")
        if len(value) * 8 > bitness:
            if bitness > 8:
                reports.error(
                    "too-long-string",
                    (arg_token.ctx_start, arg_token.ctx_end, f"Too long string: {value!r} cannot be encoded to {bitness // 8} bytes to be converted to an integer")
                )
            else:
                reports.error(
                    "too-long-string",
                    (arg_token.ctx_start, arg_token.ctx_end, f"Too long string: {value!r} cannot be encoded to a single byte to be converted to an integer")
                )
            value = value[:bitness // 8]
        value = value.ljust(bitness // 8, b"\x00")
        assert bitness in (8, 16, 32)
        if bitness == 32:
            value = value[2:] + value[:2]
        return int.from_bytes(value, byteorder="little")
    else:
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A number was expected as {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not an integer but {type(value).__name__}")
        )
        raise reports.RecoverableError()


def get_as_str(state, what, token, arg_token):
    value = wait(arg_token.resolve(state))
    if isinstance(value, str):
        return value
    else:
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A string was expected as {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not a string but {type(value).__name__}")
        )
        raise reports.RecoverableError()


from .insns import instructions  # pylint: disable=wrong-import-position
builtins = CaseInsensitiveDict(instructions)


class Metacommand:
    def __init__(self, fn, size_fn):
        self.fn = fn
        self.size_fn = size_fn
        self.name = "." + fn.__name__

        sig = inspect.signature(fn)
        assert list(sig.parameters.keys())[:1] == ["state"]

        self.min_operands = 0
        self.max_operands = 0
        self.takes_code_block = False
        for param in list(sig.parameters.values())[1:]:
            if param.annotation in (CodeBlock, "CodeBlock"):
                self.takes_code_block = True
                continue
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                self.min_operands += 1
                self.max_operands += 1
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                self.max_operands = float("+inf")


    def compile(self, state, compiler, insn):
        state = {**state, "insn": insn, "compiler": compiler}

        insn_operands = insn.operands
        code_block = None

        if self.takes_code_block:
            if insn_operands and isinstance(insn_operands[-1], CodeBlock):
                code_block = insn_operands[-1]
                insn_operands = insn_operands[:-1]
            else:
                reports.error(
                    "wrong-meta-operands",
                    (insn.ctx_start, insn.ctx_end, f"Metacommand '{insn.name.name}' expects a code block, but it was not passed")
                )
                raise reports.RecoverableError("Code block not passed")

        if self.min_operands == self.max_operands:
            expectation = f"{self.max_operands} operand" + ("s" if self.max_operands >= 2 else "")
        elif self.max_operands == float("+inf"):
            expectation = f"at least {self.min_operands} operand" + ("s" if self.min_operands >= 2 else "")
        else:
            expectation = f"from {self.min_operands} to {self.max_operands} operand" + ("s" if self.max_operands >= 2 else "")

        if len(insn_operands) < self.min_operands:
            reports.error(
                "wrong-meta-operands",
                (insn.ctx_start, insn.ctx_end, f"Too few operands passed to '{insn.name.name}': {len(insn.operands)} passed, {expectation} expected")
            )
            raise reports.RecoverableError("Too few operands")
        elif len(insn_operands) > self.max_operands:
            reports.error(
                "wrong-meta-operands",
                (insn.ctx_start, insn.ctx_end, f"Too many operands passed to '{insn.name.name}': {len(insn.operands)} passed, {expectation} expected")
            )
            raise reports.RecoverableError("Too many operands")

        operands = []
        for operand in insn_operands:
            # Stupid pylint doesn't know that decorators can mutate types
            # pylint: disable=isinstance-second-argument-not-valid-type
            if isinstance(operand, operators.immediate):
                reports.error(
                    "excess-hash",
                    (operand.ctx_start, operand.ctx_end, f"Unexpected immediate value in '{self.name}' metacommand.\nYou wrote '{operand.text()}', you probably meant '{operand.operand.text()}', proceeding under that assumption"),
                    (insn.name.ctx_start, insn.name.ctx_end, "Metacommand started here")
                )
                operands.append(operand.operand)
            else:
                operands.append(operand)

        if code_block is not None:
            operands.append(code_block)

        def fn():
            return self.fn(state, *operands)
        if self.size_fn is None:
            return Deferred[bytes](fn)
        else:
            return SizedDeferred[bytes](self.size_fn(state, *operands), fn)


def metacommand(fn=None, size=None):
    if fn is None:
        return lambda fn: metacommand(fn, size=size)

    name = "." + fn.__name__
    builtins[name] = Metacommand(fn, size)
    return fn


@metacommand(size=lambda state, *operands: len(operands))
def byte(state, *operands) -> bytes:
    def encode_i8(operand):
        value = get_as_int(state, "'.byte' operand", state["insn"], operand, bitness=8, unsigned=False, recommend_ascii=True)
        assert -2 ** 8 < value < 2 ** 8
        value %= 2 ** 8
        return struct.pack("<B", value)
    return b"".join(encode_i8(operand) for operand in operands)


@metacommand(size=lambda state, *operands: 2 * len(operands))
def word(state, *operands) -> bytes:
    def encode_i16(operand):
        value = get_as_int(state, "'.word' operand", state["insn"], operand, bitness=16, unsigned=False, recommend_ascii=True)
        assert -2 ** 16 < value < 2 ** 16
        value %= 2 ** 16
        return struct.pack("<H", value)
    return b"".join(encode_i16(operand) for operand in operands)


@metacommand(size=lambda state, *operands: 4 * len(operands))
def dword(state, *operands) -> bytes:
    def encode_i32(operand):
        value = get_as_int(state, "'.dword' operand", state["insn"], operand, bitness=32, unsigned=False, recommend_ascii=True)
        assert -2 ** 32 < value < 2 ** 32
        value %= 2 ** 32
        return struct.pack("<H", value >> 16) + struct.pack("<H", value & 0xffff)
    return b"".join(encode_i32(operand) for operand in operands)


# pylint: disable=redefined-builtin
@metacommand
def ascii(state, operand) -> bytes:
    return get_as_str(state, "'.ascii' operand", state["insn"], operand).encode("koi8-r")


@metacommand
def asciz(state, operand) -> bytes:
    return get_as_str(state, "'.asciz' operand", state["insn"], operand).encode("koi8-r") + b"\x00"


@metacommand
def blkb(state, cnt) -> bytes:
    cnt_val = get_as_int(state, "'.blkb' count", state["insn"], cnt, 16, unsigned=True)
    return b"\x00" * cnt_val


@metacommand
def blkw(state, cnt) -> bytes:
    cnt_val = get_as_int(state, "'.blkw' count", state["insn"], cnt, 16, unsigned=True)
    return b"\x00\x00" * cnt_val


@metacommand
def even(state) -> bytes:
    return b"\x00" if wait(state["emit_address"]) % 2 == 1 else b""


@metacommand
def repeat(state, cnt, body: CodeBlock) -> bytes:
    addr = state["emit_address"]
    result = b""
    cnt_val = wait(cnt.resolve(state))
    if cnt_val < 0:
        reports.error(
            "value-out-of-bounds",
            (cnt.ctx_start, cnt.ctx_end, f"Repetitions count cannot be negative ({cnt_val} given)")
        )
    for _ in range(cnt_val):
        chunk = state["compiler"].compile_block(body, addr, "repeat")
        if isinstance(chunk, BaseDeferred):
            addr += chunk.len()
        else:
            addr += len(chunk)
        result += chunk
    return result
