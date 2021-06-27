import struct

from .compiler import Compiler
from .parser import parse
from . import reports


def main():
    # compile_files(
    #     [
    #         parse("main.mac", "lbl = 'aba'\nmov r0, #a\na: inc r1\n.word lbl\n.asciz lbl\n.asciz 'hello'"),
    #         parse("additional.mac", "")
    #     ]
    # )

    path = "/home/ivanq/Documents/k1801vm1/test1.mac"

    with reports.handle_reports(reports.TextHandler()):
        with open(path) as f:
            source = f.read()
        source = """
e:
.repeat b - a {
    inc r2
}
f:

a: mov r0, #1
b: nop

.repeat f - e {
    mov r1, r2
}
""".strip()

        comp = Compiler()
        comp.add_files(
            [
                parse(path, source)
            ]
        )

        base, code = comp.link()
        with open("result.bin", "wb") as f:
            f.write(struct.pack("<HH", base, len(code)) + code)


main()
