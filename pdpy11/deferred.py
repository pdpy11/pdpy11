class NotReadyError(Exception):
    pass


def wait(deferred):
    while isinstance(deferred, BaseDeferred):
        deferred = deferred.wait()
    return deferred


def optimize(deferred):
    while isinstance(deferred, BaseDeferred):
        upd = deferred.optimize()
        if upd is deferred:
            break
        deferred = upd
    return deferred


class TryCompute:
    depth = 0

    def __enter__(self):
        self.depth += 1
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.depth -= 1
        return exc_type is NotReadyError

try_compute = TryCompute()


def not_ready():
    if try_compute.depth > 0:
        raise NotReadyError()


class BaseDeferredMetaclass(type):
    def __getitem__(cls, typ):
        return lambda *args, **kwargs: cls.construct(typ, *args, **kwargs)


class BaseDeferred(metaclass=BaseDeferredMetaclass):
    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if not args or not isinstance(args[0], type):
            raise TypeError(f"{cls.__name__} must be passed a type in brackets")  # pragma: no cover
        return super().__new__(cls)

    def __init__(self, typ: type):
        self.typ: type = typ

    @classmethod
    def construct(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def __len__(self):
        raise NotImplementedError()  # pragma: no cover

    def length(self):
        if self.typ is not bytes:  # pragma: no cover
            raise TypeError(f"Can only calculate length() of {type(self).__name__}[bytes], not {type(self).__name__}[{self.typ.__name__}]")
        return Deferred[int](lambda: len(wait(self)))

    def __repr__(self):
        raise NotImplementedError()  # pragma: no cover

    def __add__(self, rhs):
        if self.typ is int:
            poly = LinearPolynomial[self.typ]()
            poly += self
            poly += rhs
            return poly
        elif self.typ is bytes:
            if not isinstance(rhs, BaseDeferred) and not rhs:
                return self
            return Concatenator[self.typ]([self, rhs])
        else:
            raise TypeError(f"Don't know how to add {self.typ.__name__}")  # pragma: no cover

    def __radd__(self, lhs):
        if self.typ is int:
            poly = LinearPolynomial[self.typ]()
            poly += lhs
            poly += self
            return poly
        elif self.typ is bytes:
            if not isinstance(lhs, BaseDeferred) and not lhs:
                return self
            return Concatenator[self.typ]([lhs, self])
        else:
            raise TypeError(f"Don't know how to add {self.typ.__name__}")  # pragma: no cover

    def __sub__(self, rhs):
        if self.typ is int:
            return self + (-rhs)
        else:  # pragma: no cover
            raise TypeError(f"Don't know how to subtract {self.typ.__name__}")

    def __rsub__(self, lhs):
        if self.typ is int:
            return lhs + (-self)
        else:  # pragma: no cover
            raise TypeError(f"Don't know how to subtract {self.typ.__name__}")

    def __neg__(self):
        return LinearPolynomial[self.typ]({self: -1})

    def __pos__(self):
        if self.typ is not int:  # pragma: no cover
            raise TypeError(f"Don't know how to __pos__ {self.typ.__name__}")
        return self

    def __mul__(self, rhs):
        if self.typ is int and not isinstance(rhs, BaseDeferred):
            return LinearPolynomial[self.typ]({self: rhs})
        else:
            return Deferred[self.typ](lambda: wait(self) * wait(rhs))

    def __floordiv__(self, rhs):
        return Deferred[self.typ](lambda: wait(self) // wait(rhs))

    def __mod__(self, rhs):
        return Deferred[self.typ](lambda: wait(self) % wait(rhs))

    def __and__(self, rhs):
        return Deferred[self.typ](lambda: wait(self) & wait(rhs))

    def __or__(self, rhs):
        return Deferred[self.typ](lambda: wait(self) | wait(rhs))

    def __xor__(self, rhs):
        return Deferred[self.typ](lambda: wait(self) ^ wait(rhs))

    def __invert__(self):
        return Deferred[self.typ](lambda: ~wait(self))


class Deferred(BaseDeferred):
    def __init__(self, typ, fn):
        super().__init__(typ)
        self.fn = fn
        self.value = None
        self.settled = False
        self.instance_id = Deferred.next_instance_id
        Deferred.next_instance_id += 1

    @classmethod
    def construct(cls, typ, fn):  # pylint: disable=arguments-differ
        with try_compute:
            return fn()
        return cls(typ, fn)

    def __repr__(self):
        return f"d{self.instance_id}"

    def length(self):
        def fn():
            if not self.settled:
                self.wait()
            if isinstance(self.value, BaseDeferred):
                return wait(self.value.length())
            else:
                return len(self.value)
        return Deferred[int](fn)

    def wait(self):
        if self.settled:
            self.value = wait(self.value)
            return self.value
        else:
            self.value = self.fn()
            self.settled = True
            return self.value

    def optimize(self):
        if self.settled:
            self.value = optimize(self.value)
            return self.value
        else:
            with try_compute:
                try:
                    self.value = self.fn()
                    self.settled = True
                except NotReadyError:
                    pass
            return self


Deferred.next_instance_id = 1


class LinearPolynomial(BaseDeferred):
    def __init__(self, typ, coeffs=None, constant_term=0):
        if typ is not int:  # pragma: no cover
            raise TypeError(f"Can only instantiate LinearPolynomial[int], not LinearPolynomial[{typ.__name__}]")
        super().__init__(typ)
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
        for key in self.coeffs:
            if key.typ is not int:  # pragma: no cover
                raise TypeError(f"LinearPolynomial variable has an invalid type {key.typ.__name__}")
        self.coeffs = {key: value for key, value in self.coeffs.items() if value != 0}
        self.constant_term = constant_term

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
        return res or "(0)"

    def __add__(self, rhs):
        rhs = optimize(rhs)
        if not isinstance(rhs, BaseDeferred):
            return LinearPolynomial[int](self.coeffs, self.constant_term + rhs)
        if not isinstance(rhs, LinearPolynomial):
            return self + LinearPolynomial[int]({rhs: 1})
        return LinearPolynomial[int](
            list(self.coeffs.items()) + list(rhs.coeffs.items()),
            self.constant_term + rhs.constant_term
        )

    def __neg__(self):
        return LinearPolynomial[int]({key: -value for key, value in self.coeffs.items()}, -self.constant_term)

    def wait(self):
        return sum(key.wait() * value for key, value in self.coeffs.items()) + self.constant_term

    def optimize(self):
        new_coeffs = {}
        new_constant_term = self.constant_term
        for key, value in self.coeffs.items():
            key = optimize(key)
            if isinstance(key, BaseDeferred):
                if key in new_coeffs:
                    new_coeffs[key] += value
                else:
                    new_coeffs[key] = value
            else:
                new_constant_term += key * value
        self.coeffs = new_coeffs
        self.constant_term = new_constant_term
        if self.coeffs:
            return self
        else:
            return new_constant_term


class Concatenator(BaseDeferred):
    def __init__(self, typ, lst):
        super().__init__(typ)
        self.lst = lst

    def __repr__(self):
        return "+".join(map(repr, self.lst))

    def wait(self):
        return self.typ().join(map(wait, self.lst))

    def optimize(self):
        self.lst = list(map(optimize, self.lst))
        return self

    def length(self):
        total_len = 0
        for elem in self.lst:
            if isinstance(elem, BaseDeferred):
                total_len += elem.length()
            else:
                total_len += len(elem)
        return total_len

    def __add__(self, rhs):
        if isinstance(rhs, Concatenator):
            if isinstance(self.lst[-1], self.typ) and isinstance(rhs.lst[0], self.typ):
                return Concatenator[self.typ](self.lst[:-1] + [self.lst[-1] + rhs.lst[0]] + rhs.lst[1:])
            else:
                return Concatenator[self.typ](self.lst + rhs.lst)
        else:
            if isinstance(rhs, self.typ):
                if not rhs:
                    return self
                if isinstance(self.lst[-1], self.typ):
                    return Concatenator[self.typ](self.lst[:-1] + [self.lst[-1] + rhs])
            return Concatenator[self.typ](self.lst + [rhs])

    def __radd__(self, lhs):
        if isinstance(lhs, self.typ):
            if not lhs:
                return self
            if isinstance(self.lst[0], self.typ):
                return Concatenator[self.typ]([lhs + self.lst[0]] + self.lst[1:])
        return Concatenator[self.typ]([lhs] + self.lst)


class SizedDeferred(Deferred):
    def __init__(self, typ, size, fn):
        super().__init__(typ, fn)
        self.size = size

    @classmethod
    def construct(cls, typ, size, fn):  # pylint: disable=arguments-differ
        with try_compute:
            return fn()
        return cls(typ, size, fn)

    def __len__(self):
        return self.size

    def length(self):
        return self.size


class Promise(BaseDeferred):
    def __init__(self, typ, name):
        super().__init__(typ)
        self.name = name
        self.value = None
        self.settled = False

    def settle(self, value):
        assert not self.settled
        self.value = value
        self.settled = True

    def __repr__(self):
        return self.name

    def wait(self):
        if not self.settled:
            not_ready()
            raise Exception(f"Promise {self!r} is not ready")  # pragma: no cover
        return self.value

    def optimize(self):
        if self.settled:
            self.value = optimize(self.value)
            return self.value
        else:
            return self
