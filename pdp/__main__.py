from .compiler import compile_files
from .parser import parse


def main():
    # compile_files(
    #     [
    #         parse("main.mac", "lbl = 'aba'\nmov r0, #a\na: inc r1\n.word lbl\n.asciz lbl\n.asciz 'hello'"),
    #         parse("additional.mac", "")
    #     ]
    # )

    path = "/home/ivanq/Documents/k1801vm1/test.mac"

    with open(path) as f:
        compile_files(
            [
                parse(path, f.read())
            ]
        )


main()
