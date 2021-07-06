from pdpy11.parser import parse


def test_repr():
    # Note: the semicolons are actually parsed as comments, but we use them as
    # a hack so that removing all whitespace from source and repr yields
    # identical strings
    source = """
        .repeat 10 {
            nop ;
            mov r0, r1 ;
            lbl: ;
            inc pc ;
            mov #., pc ;
            inc (r0) ;
            mov #(1 + 2), r1 ;
            inc -(r1) ;
            dec (r2)+ ;
            mov #1, 4(sp) ;
            .word <12> ;
            mov #'x, r0 ;
            mov #"ab, r0
        } ;
        x = 1 ;
        .ascii "Hello, world!" ;
        .ascii 'x' ;
        .ascii "Hello," <12> "awesome world!"
    """

    assert (
        repr(parse("test.mac", source)).replace(" ", "")
        == "<test.mac>{" + source.replace(" ", "").replace("\n", "") + "}"
    )
