# All instructions are encoded into 16 bits. The numbers below are all in
# base-8, i.e. grouped by 3 bits. The characters in brackets [] denote
# individual bits. [101], for instance, is the same as 5.
#
# Letters are used to specify fields which are then filled by the assembler
# based on assembly code. The same logic applies: a single 'x' denotes three
# spare bits, a single 'x' in brackets denotes one spare bit. These can be
# mixed: 000[1oo]oo, for instance, has 8 spare bits for 'o' (which stands for
# offset).
#
#
# 's' and 'd' stand for source and destination. When a character 's' or 'd'
# occurs in the string exactly once, like in 'rts' (opcode 00020d), it is
# substituted with a register index:
#   r0 = 0
#   r1 = 1
#   r2 = 2
#   r3 = 3
#   r4 = 4
#   r5 = 5
#   sp = r6 = 6
#   pc = r7 = 7
# (This deviates from Macro-11 behavior in that r6 and r7 are defined as aliases
# for sp and pc, while Macro-11 requires using %6 or sp and %7 or pc for that
# purpose)
#
# If source or destination are encoded using 6 bits (e.g. 'ss' or 'dd'), the
# addressing mode is added before the register index. The addressing modes are:
#   0 -- register
#     For example, r2 = mode 02. This accesses the register directly.
#
#   1 -- register deferred
#     For example, (r2) = @r2 = mode 12. Using at sign @ instead of parentheses
#     () is to support legacy assemblers. This means to use the value at the
#     address specified by the register.
#
#   2 -- autoincrement
#     For example, (r2)+ = mode 22. This means to use the value at the address
#     that the register contains (like register deferred mode) and to increment
#     the register after resolving the address.
#
#     Note 1: for byte operations (e.g. movb) the register is incremented by 1,
#     for word operations it's incremented by 2. Except when sp or pc are
#     used, in which case it's always incremented by 2.
#
#     Note 2: the designed behavior for a PDP-11 machine is to resolve all
#     instruction operands from left to right, so e.g. 'mov r1, (r1)+' should
#     write word r1 at address r1 and then increase r1 by 2, but some machines
#     evaluate such instructions in different order, for example they may
#     misinterpret the above example and write word r1+2 at address r1. This
#     also applies to modes 3-5.
#
#   3 -- autoincrement deferred
#     For example, @(r2)+ = mode 32. This means to treat the word at the address
#     that the register contains as another address and use the value at the
#     latter address. Notes 1-2 apply.
#
#   4 -- autodecrement
#     For example, -(r2) = mode 42. This means to first decrement the register
#     by 1 or 2 (as in note 1) and then use the value at the address that the
#     register contains. Notes 1-2 apply.
#
#   5 -- autodecrement deferred
#     For example, @-(r2) = mode 52. This means to first decrement the register
#     by 1 or 2 (as in note 1) and then treat the word at the address that the
#     register contains as another address and use the value at the latter
#     address. Notes 1-2 apply.
#
#   6 -- index
#     For example, X(r2) = mode 62, plus word 'X' immediately after the
#     instruction. This instructs the processor to (implicitly) read the word
#     after the instruction (and advance pc by 2), then calculate the sum of
#     the said word and the register and use the result as an address which
#     contains the value to be operated on.
#
#   7 -- index deferred
#     For example, @X(r2) = mode 72, plus word 'X' immediately after the
#     instruction. Same as mode 6, but the final value is then dereferenced
#     again.
#
# These modes are usually abused to make four more modes:
#   Immediate
#     'insn #x' is an alias for 'insn (pc)+  .word x'. This causes the processor
#     to use the literal value X.
#
#   Absolute
#     'insn @#x' is an alias for 'insn @(pc)+  .word x'. This causes the
#     processor to use the value at address X.
#
#   Relative
#     'insn x' is an alias for 'insn x-.-2(pc)'. When the processor evaluates
#     the operand, pc points at the word after the instruction, i.e. .+2, so
#     the effective address is (.+2)+(x-.-2) = x. Thus, the processor uses the
#     value at address X.
#     The difference from absolute addressing is that relative addressing allows
#     code relocation. If, for example, the program was linked for base address
#     1000 but was loaded and invoked from address 2000, absolute addresses will
#     be left as-is while relative addresses will be automatically increased by
#     1000 (because pc is increased by 1000). Thus absolute addressing is
#     usually used for memory-mapped I/O while relative addressing is used for
#     program data and instructions.
#
#   Relative deferred
#     'insn @x' is an alias for 'insn @x-.-2(pc)'. This is similar to relative
#     addressing except that another level of indirection is added: the value at
#     address X is used, subject to relocation.
#
# There is no major difference between 's' and 'd' for single-operand
# instructions, except that PDPy may emit a warning if the destination is an
# immediate (#x) operand. For two-operand instructions, the source is the first
# operand and the destination is the second operand. If there's one s/d operand
# and one non-s/d operand (i.e. o/O or others), the index of the non-s/d operand
# is inferred. It is, thus, forbidden to specify a two-operand instruction
# without s/d operands.
#
#
# 'i' stands for a signed immediate value (not to be confused with immediate
# addressing) that is directly embedded into the instruction opcode. 'I' stands
# for an unsigned immediate value. You can only use compile-time constands for
# immediate values, e.g. 'emt 123' is valid code but 'emt r0' isn't (if you want
# to do something like 'emt r0' you have to patch code in runtime).
#
# 'o' is for signed branch offset, mostly for 'br' and conditional branch
# instructions. The offset is subject to .+2, i.e. the word after the
# instruction. The offset is in two's complement format, and is implicitly even,
# (i.e. the offset is multiplied by 2 when used).
#
# 'O' is for unsigned branch offset, mostly for 'sob'. The same logic applies,
# except that only backward jumps are allowed, and instead of storing how much
# to add to .+2, it stores how much to subtract from .+2. This format is
# somewhat inefficient because it can encode 'sob r0, .+2' which will just
# decrement r0 and skip to the next instruction unconditionally.
#
#
# 'S' and 'D' are like 's' and 'd' but for floating-point source and
# destination. The differences are:
#   1. In register addressing mode, the index denotes not a register but an
#      accumulator. 'r0', for instance, means 'accumulator 0'. Due to this
#      uncertainity PDPy recommends using ac0-ac5 instead of r0-r5 in this
#      context for better semantics. FP11 has 6 64-bit accumulators ac0-ac5,
#      accumulators ac6 and ac7 are non-existant and cause illegal opcode
#      exception when used.
#   2. All other modes are unaffected. However, autoincrement/autodecrement may
#      increase the address by 4 or 8, depending on the precision.
#
# When an S or D field is two bits wide, it holds a floating-point accumulator.
# Only accumulators ac0-ac3 are supported because the field is two bits wide.
# Three bit wide modes S/D are not supported.
#
#
# If an instruction takes two s operands (or, equivalently, two d operands), and
# the s operands take 12 bits all in all, then the first 6 bits are inferred to
# encode the first operand and the next 6 bits encode the second operand.
#
# If an instruction takes two S operands (or, equivalently, two D operands), and
# the S operands take 8 bits all in all, then the first 2 bits are inferred to
# encode the second operand and the next 6 bits encode the first operand.


instruction_opcodes = {
    # Halt
    "halt"  : "000000",
    # Wait until interrupt as if in a busy loop, but more efficiently
    "wait"  : "000001",
    # Return from interrupt
    "rti"   : "000002",
    # Breakpoint trap
    "bpt"   : "000003",
    # I/O trap
    "iot"   : "000004",
    # Reset external devices
    "reset" : "000005",
    # Return from trap
    "rtt"   : "000006",
    # Move from processor type
    "mfpt"  : "000007",

    # 1801VM1 and 1801VM2: Switch from halt to user mdoe
    #   000010, 000011, 000013 do the same thing on 1801VM2 and cause illegal
    #   opcode exception on 1801VM1
    "start" : "000012",
    # 'step' is to 'start' like 'rtt' is to 'rti'
    #   000014, 000015, 000017 do the same thing on 1801VM2 and cause illegal
    #   opcode exception on 1801VM1
    "step"  : "000016",

    # 1801VM2: addressless read, r0 <- (sel)
    "rd"    : "000020",
    # 1801VM2: read from user, 'mov (r5)+, r0' but the value is read from user
    # memory, not kernel memory
    "urd"   : "000021",
    # 1801VM2: move from previous pc, r0 <- pc'
    "rdpc"  : "000022",
    # 000023 does the same thing
    # 1810VM2: move from previous psw, r0 <- psw'
    "rdps"  : "000024",
    # 000025-000027 do the same thing
    # 000030 is the same as 000020 (rd)
    # 1801VM2: write to user, 'mov r0, -(r5)' but the value is written to user
    # memory, not kernel memory
    "uwr"   : "000031",
    # 1801VM2: move to previous pc, pc' <- r0
    "wrpc"  : "000032",
    # 000033 does the same thing
    # 1801VM2: move to previous psw, psw' <- r0
    "wrps"  : "000034",
    # 000035-000037 do the same thing

    # unused: 00004x
    # unused: 00005x
    # unused: 00006x
    # unused: 00007x

    # Jump
    # TODO: Warn when jumping to a register
    "jmp"   : "0001dd",
    # Return from subroutine
    "rts"   : "00020d",

    # LSI-11 reserved instructions. These do not have a particular assigned
    # mnemonic, so I used what seemed right
    #   Internal hidden temporary registers diagnostics
    "medlsi": "00021d",
    #   Jump to microlocation 3000
    "u3000" : "000220",
    # unused: 000221
    # unused: 000222
    # unused: 000223
    # unused: 000224
    # unused: 000225
    # unused: 000226
    # unused: 000227

    # Set priority level
    "spl"   : "00023I",

    # No operation (actually 'clear no flags')
    "nop"   : "000240",

    # Clear condition codes
    "clc"   : "000241",
    "clv"   : "000242",
    "clvc"  : "000243",
    "clz"   : "000244",
    "clzc"  : "000245",
    "clzv"  : "000246",
    "clzvc" : "000247",
    "cln"   : "000250",
    "clnc"  : "000251",
    "clnv"  : "000252",
    "clnvc" : "000253",
    "clnz"  : "000254",
    "clnzc" : "000255",
    "clnzv" : "000256",
    "clnzvc": "000257",
    "ccc"   : "000257",

    # Also known as nop260 (actually 'set no flags')
    # unused: 260

    # Set condition codes
    "sec"   : "000261",
    "sev"   : "000262",
    "sevc"  : "000263",
    "sez"   : "000264",
    "sezc"  : "000265",
    "sezv"  : "000266",
    "sezvc" : "000267",
    "sen"   : "000270",
    "senc"  : "000271",
    "senv"  : "000272",
    "senvc" : "000273",
    "senz"  : "000274",
    "senzc" : "000275",
    "senzv" : "000276",
    "senzvc": "000277",
    "scc"   : "000277",

    # Swap bytes
    "swab"  : "0003dd",

    # Branch unconditionally
    "br"    : "000[1oo]oo",
    # Branch if not equal
    "bne"   : "001[0oo]oo",
    # Branch if equal
    "beq"   : "001[1oo]oo",
    # Branch if greater or equal
    "bge"   : "002[0oo]oo",
    # Branch if less than
    "blt"   : "002[1oo]oo",
    # Branch if greater than
    "bgt"   : "003[0oo]oo",
    # Branch if less or equal
    "ble"   : "003[1oo]oo",

    # Jump to subroutine
    # TODO: 'jsr r, r' is invalid because you can't jump to a register. We
    # should probably emit a warning.
    "jsr"   : "004sdd",

    # Clear
    "clr"   : "0050dd",
    # Complement
    "com"   : "0051dd",
    # Increment
    "inc"   : "0052dd",
    # Decrement
    "dec"   : "0053dd",
    # Negate
    "neg"   : "0054dd",
    # Add carry
    "adc"   : "0055dd",
    # Subtract carry
    "sbc"   : "0056dd",
    # Test
    "tst"   : "0057ss",
    # Rotate right
    "ror"   : "0060dd",
    # Rotate left
    "rol"   : "0061dd",
    # Arithmetic shift right
    "asr"   : "0062dd",
    # Arithmetic shift left
    "asl"   : "0063dd",
    # Facilitate stack cleanup
    "mark"  : "0064II",
    # Move from previous instruction space
    "mfpi"  : "0065dd",
    # Move to previous instruction space
    "mtpi"  : "0066ss",
    # Sign extend
    "sxt"   : "0067dd",

    # Call to supervisor mode
    "csm"   : "0070dd",

    # unused: 0071xx

    # Test and set lsb
    "tstset": "0072dd",
    # Read/lock destination, write/unlock r0 into destination
    "wrtlck": "0073dd",

    # unused: 0074xx
    # unused: 0075xx
    # unused: 0076xx
    # unused: 0077xx

    # Move
    "mov"   : "01ssdd",
    # Compare
    "cmp"   : "02ssss",
    # Bit test
    "bit"   : "03ssss",
    # Bit clear
    "bic"   : "04ssdd",
    # Bit set
    "bis"   : "05ssdd",
    # Add
    "add"   : "06ssdd",

    # Extended instruction set (EIS):
    # Multiply
    "mul"   : "070dss",
    # Divide
    "div"   : "071dss",
    # Arithmetic shift
    "ash"   : "072dss",
    # Arithmetic shift with carry
    "ashc"  : "073dss",
    # Exclusive or
    "xor"   : "074sdd",

    # Floating-point instruction set (FIS). The register points to a working
    # area of 4 words, which contains the two operands before the operation and
    # the result afterwards. The register is adjusted, i.e. incremented by 4,
    # after the operation.
    "fadd"  : "07500d",
    "fsub"  : "07501d",
    "fmul"  : "07502d",
    "fdiv"  : "07503d",
    # unused: 07504x
    # unused: 07505x
    # unused: 07506x
    # unused: 07507x
    # unused: 0751xx
    # unused: 0752xx
    # unused: 0753xx
    # unused: 0754xx
    # unused: 0755xx
    # unused: 0756xx
    # unused: 0757xx


    # Commercial instruction set (CIS):
    # Load two descriptors
    "l2dr"  : "07602d",
    # Move character
    "movc"  : "076030",
    # Move reverse justified character
    "movrc" : "076031",
    # Move translated character
    "movtc" : "076032",
    # unused: 076033
    # unused: 076034
    # unused: 076035
    # unused: 076036
    # unused: 076037
    # Locate character
    "locc"  : "076040",
    # Skip character
    "skpc"  : "076041",
    # Scan character
    "scanc" : "076042",
    # Span character
    "spanc" : "076043",
    # Compare character
    "cmpc"  : "076044",
    # Match character
    "matc"  : "076045",
    # unused: 076046
    # unused: 076047

    # Add numeric decimal
    "addn"  : "076050",
    # Subtract numeric decimal
    "subn"  : "076051",
    # Compare numeric decimal
    "cmpn"  : "076052",
    # Convert numeric decimal to long
    "cvtnl" : "076053",
    # Convert packed decimal to numeric decimal
    "cvtpn" : "076054",
    # Convert numeric decimal to packed decimal
    "cvtnp" : "076055",
    # Arithmetic shift numeric decimal
    "ashn"  : "076056",
    # Convert long to numeric decimal
    "cvtln" : "076057",

    # Load three descriptors
    "l3dr"  : "07606d",

    # Add packed decimal
    "addp"  : "076070",
    # Subtract packed decimal
    "subp"  : "076071",
    # Compare packed decimal
    "cmpp"  : "076072",
    # Convert packed decimal to long
    "cvtpl" : "076073",
    # Multiply packed decimal
    "mulp"  : "076074",
    # Divide packed decimal
    "divp"  : "076075",
    # Arithmetic shift packed decimal
    "ashp"  : "076076",
    # Convert long to packed decimal
    "cvtlp" : "076077",

    # unused: 0761xx
    # unused: 0762xx

    # TODO: probably add operands for inline instructions?
    # Move character inline
    "movci" : "076130",
    # Move reverse justified character inline
    "movrci": "076131",
    # Move translated character inline
    "movtci": "076132",
    # unused: 076133
    # unused: 076134
    # unused: 076135
    # unused: 076136
    # unused: 076137
    # Locate character inline
    "locci" : "076140",
    # Skip character inline
    "skpci" : "076141",
    # Scan character inline
    "scanci": "076142",
    # Span character inline
    "spanci": "076143",
    # Compare character inline
    "cmpci" : "076144",
    # Match character inline
    "matci" : "076145",
    # unused: 076146
    # unused: 076147

    # Add numeric decimal inline
    "addni" : "076150",
    # Subtract numeric decimal inline
    "subni" : "076151",
    # Compare numeric decimal inline
    "cmpni" : "076152",
    # Convert numeric decimal to long inline
    "cvtnli": "076153",
    # Convert packed decimal to numeric decimal inline
    "cvtpni": "076154",
    # Convert numeric decimal to packed decimal inline
    "cvtnpi": "076155",
    # Arithmetic shift numeric decimal inline
    "ashni" : "076156",
    # Convert long to numeric decimal inline
    "cvtlni": "076157",

    # unused: 07616x

    # Add packed decimal inline
    "addpi" : "076170",
    # Subtract packed decimal inline
    "subpi" : "076171",
    # Compare packed decimal inline
    "cmppi" : "076172",
    # Convert packed decimal to long inline
    "cvtpli": "076173",
    # Multiply packed decimal inline
    "mulpi" : "076174",
    # Divide packed decimal inline
    "divpi" : "076175",
    # Arithmetic shift packed decimal inline
    "ashpi" : "076176",
    # Convert long to packed decimal inline
    "cvtlpi": "076177",

    # unused: 0762xx
    # unused: 0763xx
    # unused: 0764xx
    # unused: 0765xx

    # Maintenance examine and deposit
    "med"   : "076600",
    "med6x" : "076600",
    # PDP-11/74 CIS maintenance
    "med74c": "076601",
    # unused: 076602
    # unused: 076603
    # unused: 076604
    # unused: 076605
    # unused: 076606
    # unused: 076607
    # unused: 07661x
    # unused: 07662x
    # unused: 07663x
    # unused: 07664x
    # unused: 07665x
    # unused: 07666x
    # unused: 07667x

    # Extended function code
    "xfc"   : "0767II",

    # Subtract one and branch
    "sob"   : "077sOO",

    # Branch if non-negative
    "bpl"   : "100[0oo]oo",
    # Branch if negative
    "bmi"   : "100[1oo]oo",
    # Branch if higher
    "bhi"   : "101[0oo]oo",
    # Branch if lower or same
    "blos"  : "101[1oo]oo",
    # Branch if V cleared
    "bvc"   : "102[0oo]oo",
    # Branch if V set
    "bvs"   : "102[1oo]oo",
    # Branch if C cleared
    "bcc"   : "103[0oo]oo",
    # Branch if higher or same
    "bhis"  : "103[0oo]oo",
    # Branch if C set
    "bcs"   : "103[1oo]oo",
    # Branch if lower
    "blo"   : "103[1oo]oo",

    # Emulator trap
    "emt"   : "104[0ii]ii",
    # Generic trap
    "trap"  : "104[1ii]ii",

    # Clear byte
    "clrb"  : "1050dd",
    # Complement byte
    "comb"  : "1051dd",
    # Increment byte
    "incb"  : "1052dd",
    # Decrement byte
    "decb"  : "1053dd",
    # Negate byte
    "negb"  : "1054dd",
    # Add with carry (byte)
    "adcb"  : "1055dd",
    # Subtract with carry (byte)
    "sbcb"  : "1056dd",
    # Test byte
    "tstb"  : "1057ss",
    # Rotate right (byte)
    "rorb"  : "1060dd",
    # Rotate left (byte)
    "rolb"  : "1061dd",
    # Arithmetic shift right (byte)
    "asrb"  : "1062dd",
    # Arithmetic shift left (byte)
    "aslb"  : "1063dd",
    # Move to processor state word
    "mtps"  : "1064ss",
    # Move from previous data space
    "mfpd"  : "1065dd",
    # Move to previous data space
    "mtpd"  : "1066ss",
    # Move from processor state word
    "mfps"  : "1067dd",

    # unused: 107xxx

    # Move byte
    "movb"  : "11ssdd",
    # Compare byte
    "cmpb"  : "12ssss",
    # Bit test byte
    "bitb"  : "13ssss",
    # Bit clear byte
    "bicb"  : "14ssdd",
    # Bit set byte
    "bisb"  : "15ssdd",
    # Subtract byte
    "sub"   : "16ssdd",


    # FP11 has unusual instruction encoding. Every instruction begins with 17,
    # thus 12 bits are left for the encoding. Of those 12 bits, the last 6 are
    # always used for an operand, and the other 6 are either used for the opcode
    # or split between the opcode and the second operand. This leaves very
    # little space for the opcode, which is enough to encode most common
    # operations but not enough to encode the precision (single or double).
    #
    # Thus FP11 maintains a global precision flip-flop (denoted FD) which
    # instructs the FPU to perform single precision operations when cleared and
    # use double precision when set. But! instruction mnemonics contain a
    # precision specifier too: for instance, tstf is for single precision and
    # tstd is for double precision, but the two variants have the same opcode
    # and are thus indistinguishable by the FPU. The mnemonic specifier was
    # probably added for easier code verification, but it's really unintuitive
    # that, say, tstf may use double precision under some circumstances.
    #
    # There's isn't an easy way to check if the precisions are correct at
    # compile time, but we could check for common mistakes:
    #   1. TODO: Report a warning if the program utilizes floating point
    #      instructions but does not invoke setf or setd at least once
    #   2. TODO: Report a warning if the program utilizes any of stcfi, stcfl,
    #      stcdi, stcdl, ldcif, ldcid, ldclf, ldcld without using seti or setl
    #      at least once once. It's the same situation as with fd flip-flop,
    #      except that it's il flip-flop (sometimes called fl flip-flop, the oc
    #      docs are self-contradictory) that denotes 16-bit vs 32-bit integers
    #   3. TODO: Report a warning if the program sets precision mode using setf
    #      or setd instruction, and then uses an instruction mnemonic with
    #      different precision, if there is no branching between the two
    #      instructions, e.g. 'setf; mov r1, r2; tstd ac0'
    #   4. TODO: Same as 3. but with integer/long integer mode
    #   5. TODO: Report a warning if the program uses two instructions with
    #      different precision without branch instructions and flip-flop control
    #      instructions between them, e.g. 'tstf ac0; mov r1, r2; tstd ac1'
    #      (but 'tstf ac0; setd; tstd ac1' is fine)
    #   6. TODO: Same for integer/long integer mode
    #
    # Floating processor instruction formats ('x' is for opcode):
    #   F1: 17x[xSS]DD / 17x[xDD]SS
    #   F2: 17xxDD
    #   F3: 17x[xSS]dd / 16x[xDD]ss
    #   F4: 17xxss / 17xxdd
    #   F5: 17xxxx
    # Clear floating-point condition codes
    "cfcc"  : "170000",
    # Set (single precision) floating-point mode
    "setf"  : "170001",
    # Set (short) integer mode
    "seti"  : "170002",
    # Load microbreak register
    "ldub"  : "170003",
    # PDP-11/60: maintenance normalization shift
    "mns"   : "170004",
    # FP11-C: maintenance shift by N aka maintenance right shift
    "msn"   : "170004",
    # Load step counter
    "ldsc"  : "170004",
    # PDP-11/60: maintenance partial product
    "mpp"   : "170005",
    # Store ar register in ac0
    "sta0"  : "170005",
    # Maintenance right shift
    "mrs"   : "170006",
    # No idea what this does and whether this even exists, couldn't find docs
    "stb0"  : "170006",
    # Store qr register in ac0
    "stq0"  : "170007",
    # unused: 170010
    # Set double-precision floating-point mode
    "setd"  : "170011",
    # Set long integer mode
    "setl"  : "170012",
    # unused: 170013
    # unused: 170014
    # unused: 170015
    # unused: 170016
    # unused: 170017
    # unused: 17002x
    # unused: 17003x
    # unused: 17004x
    # unused: 17005x
    # unused: 17006x
    # unused: 17007x
    # Load FP11 program status
    "ldfps" : "1701ss",
    # Store FP11 program status
    "stfps" : "1702dd",
    # Store FP11 status
    "stst"  : "1703dd",
    # Clear
    "clrf"  : "1704DD",
    "clrd"  : "1704DD",
    # Test
    "tstf"  : "1705SS",
    "tstd"  : "1705SS",
    # Absolute value
    "absf"  : "1706DD",
    "absd"  : "1706DD",
    # Negate
    "negf"  : "1707DD",
    "negd"  : "1707DD",
    # Multiply
    "mulf"  : "171[0DD]SS",
    "muld"  : "171[0DD]SS",
    # Modulo
    "modf"  : "171[1DD]SS",
    "modd"  : "171[1DD]SS",
    # Addition
    "addf"  : "172[0DD]SS",
    "addd"  : "172[0DD]SS",
    # Load
    "ldf"   : "172[1DD]SS",
    "ldd"   : "172[1DD]SS",
    # Subtract
    "subf"  : "173[0DD]SS",
    "subd"  : "173[0DD]SS",
    # Compare
    "cmpf"  : "173[1SS]SS",
    "cmpd"  : "173[1SS]SS",
    # Store
    "stf"   : "174[0SS]DD",
    "std"   : "174[0SS]DD",
    # Divide
    "divf"  : "174[1DD]SS",
    "divd"  : "174[1DD]SS",
    # Store exponent
    "stexp" : "175[0SS]dd",
    # Store convert floating-point to integer
    "stcfi" : "175[1SS]dd",
    "stcfl" : "175[1SS]dd",
    "stcdi" : "175[1SS]dd",
    "stcdl" : "175[1SS]dd",
    # Store convert
    "stcfd" : "176[0SS]DD",
    "stcdf" : "176[0SS]DD",
    # Load exponent
    "ldexp" : "176[1DD]ss",
    # Load convert integer to floating-point
    "ldcif" : "177[0DD]ss",
    "ldcid" : "177[0DD]ss",
    "ldclf" : "177[0DD]ss",
    "ldcld" : "177[0DD]ss",
    # Load convert
    "ldcfd" : "177[1DD]SS",
    "ldcdf" : "177[1DD]SS",

    # TODO: These should all be macros
    "pop"   : "0126dd",
    "push"  : "01ss46",
    "ret"   : "000207",
    "return": "000207",
    "call"  : "0047ss",
    "sys"   : "104[1ii]ii",  # 'sys' is a synonym to 'trap' in some assemblers
    "callr" : "0001ss",
    "hlt"   : "000000",  # 'hlt' is used instead of 'halt' in PDP-11/45 maintenance reference manual
}
