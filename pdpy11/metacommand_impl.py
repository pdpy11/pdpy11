import inspect
import typing

from .deferred import Deferred, SizedDeferred, wait
from . import operators
from . import reports
from .types import CodeBlock


uint = typing.NewType("uint", int)
uint8 = typing.NewType("uint8", int)
uint16 = typing.NewType("uint16", int)
uint32 = typing.NewType("uint32", int)
int8 = typing.NewType("int8", int)
int16 = typing.NewType("int16", int)
int32 = typing.NewType("int32", int)


def get_as_int(state, what, token, arg_token, bitness, unsigned, default=None):
    value = wait(arg_token.resolve(state))

    if not isinstance(value, int):
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A number was expected as {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not an integer but {type(value).__name__}")
        )
        raise reports.RecoverableError()

    if unsigned and value < 0:
        reports.error(
            "value-out-of-bounds",
            (arg_token.ctx_start, arg_token.ctx_end, f"An unsigned integer is expected as {what}, but {value} was passed")
        )
        if default is None:
            raise reports.RecoverableError("A negative value was passed when an unsigned value was expected")
        else:
            return default

    if bitness is None:
        return value

    if value <= -2 ** bitness:
        reports.error(
            "value-out-of-bounds",
            (arg_token.ctx_start, arg_token.ctx_end, f"The value is too small: {what} {value} does not fit in {bitness} bits")
        )
        if default is None:
            raise reports.RecoverableError("Too negative value")
        else:
            return default

    if value >= 2 ** bitness:
        reports.error(
            "value-out-of-bounds",
            (arg_token.ctx_start, arg_token.ctx_end, f"The value is too large: {what} {value} does not fit in {bitness} bits")
        )
        if default is None:
            raise reports.RecoverableError("Too large value")
        else:
            return default

    return value % (2 ** bitness)


def get_as_str(state, what, token, arg_token):
    value = wait(arg_token.resolve(state))
    if isinstance(value, str):
        return value
    else:
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A string was expected for {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not a string but {type(value).__name__}")
        )
        raise reports.RecoverableError()


if hasattr(typing, "get_origin"):  # pragma: no cover
    typing_get_origin = typing.get_origin
    typing_get_args = typing.get_args
elif hasattr(typing, "_GenericAlias"):
    def typing_get_origin(tp):
        if isinstance(tp, typing._GenericAlias):
            return tp.__origin__
        else:
            return None
    def typing_get_args(tp):
        if isinstance(tp, typing._GenericAlias):
            return tp.__args__
        else:
            return ()
elif hasattr(typing, "Union"):
    def typing_get_origin(tp):
        if str(type(tp)) == "typing.Union":
            return tp.__origin__
        else:
            return None
    def typing_get_args(tp):
        if str(type(tp)) == "typing.Union":
            return tp.__args__
        else:
            return ()
else:
    raise NotImplementedError("Unsupported version of Python")


class Metacommand:
    def __init__(self, fn, name, size=None, literal_string_operand=False, raw=False):
        self.fn = fn
        self.size = size
        self.literal_string_operand = literal_string_operand
        self.name = name
        self.raw = raw

        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        assert list(sig.parameters.keys())[:1] == ["state"]

        self.min_operands = 0
        self.max_operands = 0
        self.takes_code_block = False
        self.operand_info = []

        for param in list(sig.parameters.values())[1:]:
            hint = hints[param.name]
            if typing_get_origin(hint) is typing.Union:
                hint, = [case for case in typing_get_args(hint) if case is not type(None)]
            self.operand_info.append({
                "type": hint.__supertype__ if hasattr(hint, "__supertype__") else hint,
                "hint": hint,
                "name": param.name
            })

            if hint is CodeBlock:
                self.takes_code_block = True
                continue

            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                if param.default is inspect.Parameter.empty:
                    self.min_operands += 1
                self.max_operands += 1
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                self.max_operands = float("+inf")

        if literal_string_operand:
            assert 0 <= self.min_operands <= 1 and self.max_operands == 1, "A metacommand with a literal string operand is expected to have exactly one operand (optional or not)"


    def compile_insn(self, state, insn):
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
            if self.raw:
                cooked_operands = operands
            else:
                cooked_operands = []

                for i, operand in enumerate(operands):
                    operand_info = self.operand_info[min(i, len(self.operand_info) - 1)]
                    comment = operand_info["name"].replace("_", " ")

                    if operand_info["type"] is str:
                        cooked_operand = get_as_str(state, comment, state["insn"], operand)
                    elif operand_info["type"] is int:
                        type_name = operand_info["hint"].__name__
                        unsigned = type_name.startswith("u")
                        bitness_str = type_name.replace("u", "").replace("int", "")
                        bitness = int(bitness_str) if bitness_str else None
                        cooked_operand = get_as_int(state, comment, state["insn"], operand, bitness=bitness, unsigned=unsigned)
                    elif operand_info["type"] is CodeBlock:
                        cooked_operand = operand
                    else:
                        raise TypeError(f"Invalid operand type {operand_info['type']}")  # pragma: no cover

                    cooked_operands.append(cooked_operand)

            try:
                return self.fn(state, *cooked_operands)
            except reports.RecoverableError:
                return b""


        size = self.size(state, *operands) if callable(self.size) else self.size
        if size is None:
            return Deferred[bytes](fn)
        else:
            return SizedDeferred[bytes](size, fn)


metacommands = {}


def _metacommand_impl(fn, no_dot=False, alias=None, **kwargs):
    name = ("" if no_dot else ".") + fn.__name__.rstrip("_")

    if isinstance(alias, str):
        aliases = [alias]
    elif alias is None:
        aliases = []
    else:
        aliases = alias

    cmd = Metacommand(fn, name, **kwargs)
    for command_name in aliases + [name]:
        metacommands[command_name] = cmd

    # That is not to override globals with the same name, e.g. list
    return __builtins__.get(fn.__name__, None)


def metacommand(fn=None, **kwargs):
    if fn is None:
        # This looks like a false positive from pylint
        return lambda fn: metacommand(fn, **kwargs)  # pylint: disable=unnecessary-lambda
    else:
        return _metacommand_impl(fn, **kwargs)
