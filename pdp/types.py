from .context import Context


class Token:
    def __init__(self, ctx_start, ctx_end, *args, **kwargs):
        assert ctx_start is None or isinstance(ctx_start, Context)
        assert ctx_end is None or isinstance(ctx_end, Context)
        self.ctx_start = None if ctx_start is None else ctx_start.save()
        self.ctx_end = None if ctx_end is None else ctx_end.save()
        self.init(*args, **kwargs)

    def init(self):
        pass


class Instruction(Token):
    # pylint: disable=arguments-differ
    def init(self, name, operands):
        self.name = name
        self.operands = operands


    def __repr__(self):
        if self.operands:
            return f"{self.name} {', '.join(map(repr, self.operands))}"
        else:
            return f"{self.name}"


    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.operands) == (rhs.name, rhs.operands)


class Register(Token):
    inline_length = 0

    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name
        self.idx = {
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
        }[name.lower()]

    def __repr__(self):
        return f"{self.name}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name


class SimpleAddressingMode:
    def encode_mode(self):
        return (self.mode_code << 3) | self.reg.idx


class AddressingModes:
    class Register(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 0

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return repr(self.reg)

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class RegisterDeferred(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 1

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return f"({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Autoincrement(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 2

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return f"({self.reg})+"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class AutoincrementDeferred(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 3

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return f"@({self.reg})+"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Autodecrement(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 4

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return f"-({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class AutodecrementDeferred(Token, SimpleAddressingMode):
        inline_length = 0
        mode_code = 5

        # pylint: disable=arguments-differ
        def init(self, reg: Register):
            self.reg: Register = reg

        def __repr__(self):
            return f"@-({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.reg == rhs.reg


    class Index(Token, SimpleAddressingMode):
        inline_length = 2
        mode_code = 6

        # pylint: disable=arguments-differ
        def init(self, reg: Register, index):
            self.reg: Register = reg
            self.index = index

        def __repr__(self):
            return f"{self.index}({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and (self.reg, self.index) == (rhs.reg, rhs.index)


    class IndexDeferred(Token, SimpleAddressingMode):
        inline_length = 2
        mode_code = 7

        # pylint: disable=arguments-differ
        def init(self, reg: Register, index):
            self.reg: Register = reg
            self.index = index

        def __repr__(self):
            return f"@{self.index}({self.reg})"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and (self.reg, self.index) == (rhs.reg, rhs.index)


    class Immediate(Token):
        inline_length = 2

        # pylint: disable=arguments-differ
        def init(self, value):
            self.value = value

        def __repr__(self):
            return f"#{self.value}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.value == rhs.value

        def encode_mode(self):
            return 0o27


    class Absolute(Token):
        inline_length = 2

        # pylint: disable=arguments-differ
        def init(self, addr):
            self.addr = addr

        def __repr__(self):
            return f"@#{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def encode_mode(self):
            return 0o37


    class Relative(Token):
        inline_length = 2

        # pylint: disable=arguments-differ
        def init(self, addr):
            self.addr = addr

        def __repr__(self):
            return f"{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def encode_mode(self):
            return 0o67


    class RelativeDeferred(Token):
        inline_length = 2

        # pylint: disable=arguments-differ
        def init(self, addr):
            self.addr = addr

        def __repr__(self):
            return f"@{self.addr}"

        def __eq__(self, rhs):
            return isinstance(rhs, type(self)) and self.addr == rhs.addr

        def encode_mode(self):
            return 0o77


class InstructionPointer(Token):
    def __repr__(self):
        return "."

    def __eq__(self, rhs):
        return isinstance(rhs, type(self))

    def get(self):
        raise NotImplementedError("InstructionPointer.get")

    def try_get(self):
        raise NotImplementedError("InstructionPointer.try_get")


class Symbol(Token):
    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name

    def __repr__(self):
        return self.name

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name

    def get(self):
        raise NotImplementedError("Symbol.get")

    def try_get(self):
        raise NotImplementedError("Symbol.try_get")


class Label(Token):
    # pylint: disable=arguments-differ
    def init(self, name: str):
        self.name: str = name
        self.local: bool = name[0].isdigit()

    def __repr__(self):
        return f"{self.name}:"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.name == rhs.name


class Assignment(Token):
    # pylint: disable=arguments-differ
    def init(self, name: Symbol, value):
        self.name: Symbol = name
        self.value = value

    def __repr__(self):
        return f"{self.name} = {self.value}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.name, self.value) == (rhs.name, rhs.value)


class Operator(Token):
    # pylint: disable=arguments-differ
    def init(self, lhs: Token, rhs: Token, operator: str):
        self.lhs: Token = lhs
        self.rhs: Token = rhs
        self.operator: str = operator

    def __repr__(self):
        return f"({self.lhs} {self.operator} {self.rhs})"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.lhs, self.rhs, self.operator) == (rhs.lhs, rhs.rhs, rhs.operator)

    def get(self):
        raise NotImplementedError("Operator.get")

    def try_get(self):
        raise NotImplementedError("Operator.try_get")


class CodeBlock(Token):
    # pylint: disable=arguments-differ
    def init(self, insns):
        self.insns = insns

    def __repr__(self):
        return "{ " + "; ".join(map(repr, self.insns)) + " }"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.insns == rhs.insns


class String(Token):
    # pylint: disable=arguments-differ
    def init(self, string: str):
        self.string = string

    def __repr__(self):
        return f"\"{self.string}\""

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.string == rhs.string

    def get(self):
        return self.string

    def try_get(self):
        return self.get()


class Number(Token):
    # pylint: disable=arguments-differ
    def init(self, representation):
        self.representation = representation

    def __repr__(self):
        return f"{self.representation}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and self.representation == rhs.representation

    def get(self):
        if self.representation.endswith("."):
            return int(self.representation[:-1])
        else:
            return int(self.representation, 8)

    def try_get(self):
        return self.get()


class File:
    def __init__(self, filename, body):
        self.filename = filename
        self.body = body

    def __repr__(self):
        return f"<{self.filename}> {self.body}"

    def __eq__(self, rhs):
        return isinstance(rhs, type(self)) and (self.filename, self.body) == (rhs.filename, rhs.body)
