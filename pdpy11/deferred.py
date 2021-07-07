class NotReadyError(Exception):
    pass


def wait(deferred):
    while isinstance(deferred, BaseDeferred):
        deferred = deferred.wait()
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


class Awaiting:
    awaiting_stack = []

    def __init__(self, deferred):
        self.deferred = deferred

    def __enter__(self):
        assert not self.deferred.is_awaiting
        self.deferred.is_awaiting = True
        Awaiting.awaiting_stack.append(self.deferred)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        assert Awaiting.awaiting_stack.pop() is self.deferred
        self.deferred.is_awaiting = False


def not_ready():
    if try_compute.depth > 0:
        raise NotReadyError()


class BaseDeferredMetaclass(type):
    def __getitem__(cls, typ):
        if not isinstance(typ, type):
            raise TypeError(f"{cls.__name__} must be passed a type in brackets, not {typ}")  # pragma: no cover
        return lambda *args, **kwargs: cls.construct(typ, *args, **kwargs)


class BaseDeferred(metaclass=BaseDeferredMetaclass):
    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if not args or not isinstance(args[0], type):
            raise TypeError(f"{cls.__name__} must be passed a type in brackets")  # pragma: no cover
        return super().__new__(cls)

    def __init__(self, typ: type):
        self.typ: type = typ
        self.is_awaiting = False

    @classmethod
    def construct(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def wait(self):
        with Awaiting(self):
            return self._wait()

    def try_compute(self):
        raise NotImplementedError(type(self).__name__ + ".try_compute()")  # pragma: no cover

    def get_current_best_estimate(self):
        raise NotImplementedError(type(self).__name__ + ".get_current_best_estimate()")  # pragma: no cover

    def _wait(self):
        raise NotImplementedError()  # pragma: no cover

    def __len__(self):
        raise NotImplementedError()  # pragma: no cover

    def length(self):
        if self.typ is not bytes:  # pragma: no cover
            raise TypeError(f"Can only calculate length() of {type(self).__name__}[bytes], not {type(self).__name__}[{self.typ.__name__}]")
        return Deferred[int](lambda: len(wait(self)))

    def __repr__(self):
        raise NotImplementedError()  # pragma: no cover

    def __add__(self, rhs):
        if isinstance(rhs, LinearPolynomial):
            return NotImplemented
        elif self.typ is int:
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
            # TODO: maybe it makes sense not to await LinearPolynomial when
            # multiplying Deferred by LinearPolynomial (and the other way round)
            return Deferred[self.typ](lambda: wait(self) * wait(rhs))

    def __rmul__(self, lhs):
        if self.typ is int:
            return LinearPolynomial[self.typ]({self: lhs})
        else:
            raise TypeError(f"Don't know how to multiply {self.typ.__name__}")


class Deferred(BaseDeferred):
    def __init__(self, typ, fn, name=None):
        super().__init__(typ)
        self.fn = fn
        self.value = None
        self.settled = False
        self.name = name or f"d{Deferred.next_instance_id}"
        Deferred.next_instance_id += 1

    @classmethod
    def construct(cls, *args):  # pylint: disable=arguments-differ
        tmp = cls(*args)
        with try_compute:
            return tmp.wait()
        return tmp

    def __repr__(self):
        if self.settled:
            return f"{self.name}[={self.value!r}]"
        else:
            return self.name

    def length(self):
        def fn():
            if not self.settled:
                self.wait()
            if isinstance(self.value, BaseDeferred):
                return wait(self.value.length())
            else:
                return len(self.value)
        return Deferred[int](fn)

    def _wait(self):
        if self.settled:
            return self.value
        else:
            self.value = self.fn()
            self.settled = True
            return self.value

    def try_compute(self):
        if not self.settled:
            with try_compute, Awaiting(self):
                try:
                    self.value = self.fn()
                    self.settled = True
                except NotReadyError:
                    return self
        if isinstance(self.value, BaseDeferred):
            self.value = self.value.try_compute()
        return self.value

    def get_current_best_estimate(self):
        if not self.settled:
            return self
        return self.value


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
        for key, value in self.coeffs.items():
            if key.typ is not int:  # pragma: no cover
                raise TypeError(f"LinearPolynomial variable has an invalid type {key.typ.__name__}")
            if isinstance(key, LinearPolynomial):
                raise TypeError("LinearPolynomial variable cannot be a linear polynomial itself")  # pragma: no cover
            if not isinstance(value, int):  # pragma: no cover
                raise TypeError(f"LinearPolynomial coefficient has an invalid type {type(value).__name__}")
        self.coeffs = {key: value for key, value in self.coeffs.items() if value != 0}
        self.constant_term = constant_term
        if not isinstance(constant_term, int):  # pragma: no cover
            raise TypeError(f"LinearPolynomial constant term has an invalid type {type(constant_term).__name__}")

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
        if isinstance(rhs, BaseDeferred):
            rhs = rhs.get_current_best_estimate()
        if not isinstance(rhs, BaseDeferred):
            return LinearPolynomial[int](self.coeffs, self.constant_term + rhs)
        if not isinstance(rhs, LinearPolynomial):
            rhs = LinearPolynomial[int]({rhs: 1})
        return LinearPolynomial[int](
            list(self.coeffs.items()) + list(rhs.coeffs.items()),
            self.constant_term + rhs.constant_term
        )

    def __radd__(self, lhs):
        return self + lhs

    def __mul__(self, rhs):
        if isinstance(rhs, BaseDeferred):
            rhs = rhs.get_current_best_estimate()
        if isinstance(rhs, BaseDeferred):
            if self.coeffs:
                return Deferred[int](lambda: wait(self) * wait(rhs))
            else:
                return rhs * self.constant_term
        return LinearPolynomial[int]({key: value * rhs for key, value in self.coeffs.items()}, self.constant_term * rhs)

    def __rmul__(self, lhs):
        assert isinstance(lhs, self.typ)
        return LinearPolynomial[int]({key: value * lhs for key, value in self.coeffs.items()}, self.constant_term * lhs)


    def __neg__(self):
        return LinearPolynomial[int]({key: -value for key, value in self.coeffs.items()}, -self.constant_term)

    def _wait(self):
        self.try_compute()
        return sum(key.wait() * value for key, value in self.coeffs.items()) + self.constant_term


    def try_compute(self):
        new_coeffs = []
        new_constant_term = self.constant_term

        for key, value in self.coeffs.items():
            key = key.get_current_best_estimate()
            if isinstance(key, LinearPolynomial):
                new_coeffs += [(key1, value1 * value) for key1, value1 in key.coeffs.items()]
                new_constant_term += key.constant_term * value
            elif isinstance(key, BaseDeferred):
                new_coeffs.append((key, value))
            else:
                new_constant_term += key * value

        new_value = LinearPolynomial[int](new_coeffs, new_constant_term)
        self.coeffs = new_value.coeffs
        self.constant_term = new_value.constant_term
        return self.get_current_best_estimate()

    def get_current_best_estimate(self):
        if self.coeffs:
            return self
        else:
            return self.constant_term



class Concatenator(BaseDeferred):
    def __init__(self, typ, lst):
        super().__init__(typ)
        self.lst = lst

    def __repr__(self):
        return "+".join(map(repr, self.lst))

    def _wait(self):
        return self.typ().join(map(wait, self.lst))

    def try_compute(self):
        self.lst = [
            elem.get_current_best_estimate() if isinstance(elem, BaseDeferred) else elem
            for elem in self.lst
        ]
        return self.get_current_best_estimate()

    def get_current_best_estimate(self):
        if all(not isinstance(elem, BaseDeferred) for elem in self.lst):
            return self.typ().join(self.lst)
        else:
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
        tmp = cls(typ, size, fn)
        with try_compute:
            return tmp.wait()
        return tmp

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

    def _wait(self):
        if not self.settled:
            not_ready()
            raise Exception(f"Promise {self!r} is not ready")  # pragma: no cover
        return self.value

    def try_compute(self):
        if self.settled and isinstance(self.value, BaseDeferred):
            self.value = self.value.get_current_best_estimate()
        return self.get_current_best_estimate()

    def get_current_best_estimate(self):
        if self.settled:
            return self.value
        else:
            return self
