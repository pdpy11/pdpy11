instruction_opcodes = dict(
    halt   = "000000",
    wait   = "000001",
    rti    = "000002",
    bpt    = "000003",
    iot    = "000004",
    reset  = "000005",
    rtt    = "000006",
    mfpt   = "000007",
    # unused: 00001x
    # unused: 00002x
    # unused: 00003x
    # unused: 00004x
    # unused: 00005x
    # unused: 00006x
    # unused: 00007x
    # TODO: Macro-11 apparently has 'callr' instruction which is equivalent to
    # 'jmp r0' (or maybe 'jmp rn'), which is undefined because you can't jump to
    # a register. I should figure out what it does.
    # TODO: Warn when jumping to a register?
    jmp    = "0001dd",
    rts    = "00020d",
    # unused: 00021x
    # unused: 00022x
    spl    = "00023I",
    nop    = "000240",
    clc    = "000241",
    clv    = "000242",
    clvc   = "000243",
    clz    = "000244",
    clzc   = "000245",
    clzv   = "000246",
    clzvc  = "000247",
    cln    = "000250",
    clnc   = "000251",
    clnv   = "000252",
    clnvc  = "000253",
    clnz   = "000254",
    clnzc  = "000255",
    clnzv  = "000256",
    ccc    = "000257",
    # unused: 260
    sec    = "000261",
    sev    = "000262",
    sevc   = "000263",
    sez    = "000264",
    sezc   = "000265",
    sezv   = "000266",
    sezvc  = "000267",
    sen    = "000270",
    senc   = "000271",
    senv   = "000272",
    senvc  = "000273",
    senz   = "000274",
    senzc  = "000275",
    senzv  = "000276",
    scc    = "000277",
    swab   = "0003dd",
    br     = "000[1oo]oo",
    bne    = "001[0oo]oo",
    beq    = "001[1oo]oo",
    bge    = "002[0oo]oo",
    blt    = "002[1oo]oo",
    bgt    = "003[0oo]oo",
    ble    = "003[1oo]oo",
    jsr    = "004sdd",  # TODO: 'jsr r, r' is invalid because you can't jump to a register. We should probably emit a warning.
    clr    = "0050dd",
    com    = "0051dd",
    inc    = "0052dd",
    dec    = "0053dd",
    neg    = "0054dd",
    adc    = "0055dd",
    sbc    = "0056dd",
    tst    = "0057dd",
    ror    = "0060dd",
    rol    = "0061dd",
    asr    = "0062dd",
    asl    = "0063dd",
    mark   = "0064II",
    mfpi   = "0065ss",
    mtpi   = "0066dd",
    sxt    = "0067dd",
    csm    = "0070dd",
    # TODO: maybe there are other instructions, but I'm yet to find docs on those
    # unused: 0071xx
    tstset = "0072dd",
    wrtlck = "0073dd",
    # unused: 0074xx
    # unused: 0075xx
    # unused: 0076xx
    # unused: 0077xx
    mov    = "01ssdd",
    cmp    = "02ssdd",
    bit    = "03ssdd",
    bic    = "04ssdd",
    bis    = "05ssdd",
    add    = "06ssdd",
    mul    = "070dss",
    div    = "071dss",
    ash    = "072dss",
    ashc   = "073dss",
    xor    = "074sdd",
    # TODO: 075xxx is floating-point instruction set. The insns below may or may
    # not be correct. 'r' is either destination or source, idk, maybe not even
    # CPU registers but FPU registers, I should figure that out.
    #   fadd = 07500r
    #   fsub = 07501r
    #   fmul = 07502r
    #   fdiv = 07503r
    # unused: 075xxx
    # TODO: 076xxx is commerical instruction set (CIS)
    # unused: 0760xx
    # unused: 0761xx
    # unused: 0762xx
    # unused: 0763xx
    # unused: 0764xx
    # unused: 0765xx
    # TODO: figure out the format of this instruction. Macro-11 has two
    # instructions for this: med6x = 076600 and med74c = 076601
    med    = "076600",
    # TODO: xfc = 076700? I should figure out the operands
    # unused: 0767xx
    sob    = "077sOO",
    bpl    = "100[0oo]oo",
    bmi    = "100[1oo]oo",
    bhi    = "101[0oo]oo",
    blos   = "101[1oo]oo",
    bvc    = "102[0oo]oo",
    bvs    = "102[1oo]oo",
    bcc    = "103[0oo]oo",
    bhis   = "103[0oo]oo",
    bcs    = "103[1oo]oo",
    blo    = "103[1oo]oo",
    emt    = "104[0ii]ii",
    trap   = "104[1ii]ii",
    clrb   = "1050dd",
    comb   = "1051dd",
    incb   = "1052dd",
    decb   = "1053dd",
    negb   = "1054dd",
    adcb   = "1055dd",
    sbcb   = "1056dd",
    tstb   = "1057dd",
    rorb   = "1060dd",
    rolb   = "1061dd",
    asrb   = "1062dd",
    aslb   = "1063dd",
    mtps   = "1064ss",
    mfpd   = "1065ss",
    mtpd   = "1066dd",
    mfps   = "1067dd",
    # unused: 107xxx
    movb   = "11ssdd",
    cmpb   = "12ssdd",
    bitb   = "13ssdd",
    bicb   = "14ssdd",
    bisb   = "15ssdd",
    sub    = "16ssdd",
    # TODO: FP11 (floating point coprocessor)
    # unused: 170000
    # unused: 170001
    # unused: 170002
    ldub   = "170003",
    mns    = "170004",
    mpp    = "170005",
    # unused: 170006
    # unused: 170007
    # unused: 17001x
    # unused: 17002x
    # unused: 17003x
    # unused: 17004x
    # unused: 17005x
    # unused: 17006x
    # unused: 17007x

    # absd = 170600
    # absf = 170600
    # addd = 172000
    # addf = 172000
    # cfcc = 170000
    # clrd = 170400
    # clrf = 170400
    # cmpd = 173400
    # cmpf = 173400
    # divd = 174400
    # divf = 174400
    # ldcdf = 177400
    # ldcfd = 177400
    # ldcid = 177000
    # ldcif = 177000
    # ldcld = 177000
    # ldclf = 177000
    # ldd = 172400
    # ldexp = 176400
    # ldf = 172400
    # ldfps = 170100
    # modd = 171400
    # modf = 171400
    # muld = 171000
    # mulf = 171000
    # negd = 170700
    # negf = 170700
    # setd = 170011
    # setf = 170001
    # seti = 170002
    # setl = 170012
    # sta0 = 170005
    # stb0 = 170006
    # stcdf = 176000
    # stcdi = 175400
    # stcdl = 175400
    # stcfd = 176000
    # stcfi = 175400
    # stcfl = 175400
    # std = 174000
    # stexp = 175000
    # stf = 174000
    # stfps = 170200
    # stst = 170300
    # subd = 173000
    # subf = 173000
    # tstd = 170500
    # tstf = 170500

    # TODO: These should all be macros
    pop    = "0126dd",
    push   = "01ss46",
    ret    = "000207",
    call   = "0047ss",
    sys    = "104[1ii]ii",  # 'sys' is a synonym to 'trap' in some assemblers
)
