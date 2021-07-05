class NeedFreeVariables(Exception):
    def __init__(self, variables):
        super().__init__(variables)
        self.variables = variables


class FreeVariable:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def to_polynomial(self):
        return LinearPolynomial({self: 1})


class LinearPolynomial:
    def __init__(self, coeffs=None, constant_term=0):
        if coeffs is None:
            self.coeffs = {}
        elif isinstance(coeffs, dict):
            self.coeffs = coeffs
        else:
            self.coeffs = {}
            for key, value in coeffs:
                if key in self.coeffs:
                    self.coeffs[key] += value
                else:
                    self.coeffs[key] = value

        for key, value in self.coeffs.items():
            assert isinstance(key, FreeVariable)
            assert isinstance(value, int)
        assert isinstance(constant_term, int)

        self.coeffs = {key: value for key, value in self.coeffs.items() if value != 0}
        self.constant_term = constant_term


    def is_constant(self):
        return self.coeffs == {}


    def to_polynomial(self):
        return self


    def __repr__(self):
        lst = []
        for key, value in self.coeffs.items():
            lst.append(
                ("+" if value >= 0 else "")
                + {1: "", -1: "-"}.get(value, str(value) + "*")
                + repr(key)
            )
        if self.constant_term >= 0:
            lst.append(f"+{self.constant_term}")
        else:
            lst.append(str(self.constant_term))
        res = "".join(lst)
        if res[:1] == "+":
            res = res[1:]
        return "(0)" if res == "0" else res


    def __add__(self, rhs):
        if isinstance(rhs, int):
            return LinearPolynomial(self.coeffs, self.constant_term + rhs)

        assert isinstance(rhs, LinearPolynomial)

        poly = LinearPolynomial(
            list(self.coeffs.items()) + list(rhs.coeffs.items()),
            self.constant_term + rhs.constant_term
        )
        if poly.is_constant():
            return poly.constant_term
        else:
            return poly

    def __radd__(self, lhs):
        return self + lhs


    def __sub__(self, rhs):
        return self + (-rhs)

    def __rsub__(self, lhs):
        return lhs + (-self)


    def __mul__(self, coeff):
        assert isinstance(coeff, int)
        if coeff == 0:
            return 0
        return LinearPolynomial(
            {key: value * coeff for key, value in self.coeffs.items()},
            self.constant_term * coeff
        )

    def __rmul__(self, lhs):
        return self * lhs


    def __pos__(self):
        return self

    def __neg__(self):
        return LinearPolynomial(
            {key: -value for key, value in self.coeffs.items()},
            -self.constant_term
        )


    def compute(self):
        assert self.coeffs
        raise NeedFreeVariables(list(self.coeffs.keys()))


def compute_if_poly(obj):
    if isinstance(obj, LinearPolynomial):
        return obj.compute()
    else:
        return obj
