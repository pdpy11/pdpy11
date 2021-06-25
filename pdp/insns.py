import struct

from .containers import CaseInsensitiveDict
from .deferred import SizedDeferred
from . import reports


instruction_opcodes = dict(
    halt  = "000000",
    wait  = "000001",
    rti   = "000002",
    bpt   = "000003",
    iot   = "000004",
    reset = "000005",
    rtt   = "000006",
    mfpt  = "000007",
    jmp   = "0001dd",
    rts   = "00020d",
    spl   = "00023i",
    # TODO: nop
    clc   = "000241",
    clv   = "000242",
    clvc  = "000243",
    clz   = "000244",
    clzc  = "000245",
    clzv  = "000246",
    clzvc = "000247",
    cln   = "000250",
    clnc  = "000251",
    clnv  = "000252",
    clnvc = "000253",
    clnz  = "000254",
    clnzc = "000255",
    clnzv = "000256",
    ccc   = "000257",
    # TODO: nop 260
    sec   = "000261",
    sev   = "000262",
    sevc  = "000263",
    sez   = "000264",
    sezc  = "000265",
    sezv  = "000266",
    sezvc = "000267",
    sen   = "000270",
    senc  = "000271",
    senv  = "000272",
    senvc = "000273",
    senz  = "000274",
    senzc = "000275",
    senzv = "000276",
    scc   = "000277",
    swab  = "0003dd",
    br    = "000[1oo]oo",
    bne   = "001[0oo]oo",
    beq   = "001[1oo]oo",
    bge   = "002[0oo]oo",
    blt   = "002[1oo]oo",
    bgt   = "003[0oo]oo",
    ble   = "003[1oo]oo",
    jsr   = "004sdd",
    clr   = "0050dd",
    com   = "0051dd",
    inc   = "0052dd",
    dec   = "0053dd",
    neg   = "0054dd",
    adc   = "0055dd",
    sbc   = "0056dd",
    tst   = "0057dd",
    ror   = "0060dd",
    rol   = "0061dd",
    asr   = "0062dd",
    asl   = "0063dd",
    mark  = "0064ii",
    mfpi  = "0065ss",
    mtpi  = "0067dd",
    sxt   = "0067dd",
    csm   = "0070dd",
    mov   = "01ssdd",
    cmp   = "02ssdd",
    bit   = "03ssdd",
    bic   = "04ssdd",
    bis   = "05ssdd",
    add   = "06ssdd",
    mul   = "070dss",
    div   = "071dss",
    ash   = "072dss",
    ashc  = "073dss",
    xor   = "074sdd",
    med   = "076600", # TODO?
    sob   = "077doo",
    bpl   = "100[0oo]oo",
    bmi   = "100[1oo]oo",
    bhi   = "101[0oo]oo",
    blos  = "101[1oo]oo",
    bvc   = "102[0oo]oo",
    bvs   = "102[1oo]oo",
    bcc   = "103[0oo]oo",
    bhis  = "103[0oo]oo",
    bcs   = "103[1oo]oo",
    blo   = "103[1oo]oo",
    emt   = "104[0ii]ii",
    trap  = "104[1ii]ii",
    clrb  = "1050dd",
    comb  = "1051dd",
    incb  = "1052dd",
    decb  = "1053dd",
    negb  = "1054dd",
    adcb  = "1055dd",
    sbcb  = "1056dd",
    tstb  = "1057dd",
    rorb  = "1060dd",
    rolb  = "1061dd",
    asrb  = "1062dd",
    aslb  = "1063dd",
    mtps  = "1064ss",
    mfpd  = "1065ss",
    mtpd  = "1066dd",
    mfps  = "1067dd",
    movb  = "11ssdd",
    cmpb  = "12ssdd",
    bitb  = "13ssdd",
    bicb  = "14ssdd",
    bisb  = "15ssdd",
    sub   = "16ssdd",
    ldub  = "170003",
    mns   = "170004",
    mpp   = "170005",
    # TODO: floating-point instructions
    # TODO: xfc


    # TODO: Damn, I'm just too lazy to implement all these as macros. Will do that later.
    pop   = "0126dd",
    push  = "01ss46",
    ret   = "000206",
    call  = "0046ss",
    nop   = "000240"
)



class RegisterOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char

class RegisterModeOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char

class OffsetOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char

class ImmediateOperandStub:
    def __init__(self, pattern_char):
        self.pattern_char = pattern_char


# def patch_insn(stub, pattern, value):
#     enc = value.encode_mode()
#     pattern[stub.pattern_char]

#     print(pattern, stub.pattern_char, value, enc)
#     raise NotImplementedError()


class Instruction:
    def __init__(self, name, opcode_pattern, src_operand, dst_operand):
        self.name = name
        self.opcode_pattern = opcode_pattern
        self.src_operand = src_operand
        self.dst_operand = dst_operand


    def substitute(self, insn):
        operands = [op for op in (self.src_operand, self.dst_operand) if op is not None]

        if len(insn.operands) < len(operands):
            reports.error(
                (insn.ctx_start, insn.ctx_end, f"Too few operands for '{self.name}' instruction: {len(operands)} expected, {len(insn.operands)} given")
            )
            return None
        elif len(insn.operands) > len(operands):
            reports.error(
                (insn.ctx_start, insn.ctx_end, f"Too many operands for '{self.name}' instruction: {len(operands)} expected, {len(insn.operands)} given")
            )
            return None

        chunk_length = 2 + sum(operand.inline_length for operand in insn.operands)
        def encode():
            pattern = self.opcode_pattern
            operands_encoding = b""
            for operand, value in zip(operands, insn.operands):
                if operand:
                    pattern = patch_insn(operand, pattern, value)
                    operands_encoding += operand.encode_inline()
            assert pattern.isdigit()
            return struct.pack("<H", int(pattern, 2)) + operands_encoding
        return SizedDeferred(chunk_length, encode)




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

        if "o" in opcode_pattern:
            if src_operand is None:
                src_operand = OffsetOperandStub("o")
            else:
                assert dst_operand is None
                dst_operand = OffsetOperandStub("o")

        if "i" in opcode_pattern:
            assert "o" not in opcode_pattern
            assert src_operand is None
            src_operand = ImmediateOperandStub("i")

        instructions[insn_name] = Instruction(insn_name, opcode_pattern, src_operand, dst_operand)


init()
