class NotReadyError(BaseException):
    pass


class BaseDeferred:
    def __len__(self):
        raise NotReadyError()

    def len(self):
        raise NotImplementedError()

    def __repr__(self):
        raise NotImplementedError()

    def __add__(self, rhs):
        poly = LinearPolynomial()
        poly += self
        poly += rhs
        return poly


class Deferred(BaseDeferred):
    def __new__(cls, fn):
        # Maybe data is already available? I bet most users wouldn't even notice
        # a problem for half a year if deferred calculations were disabled
        return fn()

    def __init__(self, fn):
        self.fn = fn
        self.value = None
        self.has_value = False
        self.instance_id = Deferred.next_instance_id
        Deferred.next_instance_id += 1

    def len(self):
        return Deferred(lambda: len(self._get()))

    def __repr__(self):
        return f"d{self.instance_id}"

Deferred.next_instance_id = 1


class LinearPolynomial(BaseDeferred):
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
        self.coeffs = {key: value for key, value in self.coeffs.items() if value != 0}
        self.constant_term = constant_term

    def len(self):
        raise TypeError("A numeric value has no length")

    def __repr__(self):
        lst = []
        for key, value in self.coeffs.items():
            lst.append(
                ("+" if value >= 0 else "")
                + (str(value) + "*" if value != 1 else "")
                + repr(key)
            )
        if self.constant_term >= 0:
            lst.append(f"+{self.constant_term}")
        else:
            lst.append(str(self.constant_term))
        res = "".join(lst)
        if res[:1] == "+":
            res = res[1:]
        return res or "(0)"

    def __add__(self, rhs):
        if not isinstance(rhs, BaseDeferred):
            return LinearPolynomial(self.coeffs, self.constant_term + rhs)
        if not isinstance(rhs, LinearPolynomial):
            return self + LinearPolynomial({rhs: 1})
        return LinearPolynomial(
            list(self.coeffs.items()) + list(rhs.coeffs.items()),
            self.constant_term + rhs.constant_term
        )


class SizedDeferred(Deferred):
    # pylint: disable=unused-argument
    def __new__(cls, size, fn):
        return super().__new__(cls, fn)

    def __init__(self, size, fn):
        super().__init__(fn)
        self.size = size

    def __len__(self):
        return self.size

    def len(self):
        return self.size


class Promise(BaseDeferred):
    def __init__(self, name):
        self.name = name

    def len(self):
        raise NotImplementedError()

    def __repr__(self):
        return self.name
