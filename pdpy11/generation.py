from enum import Enum


class GenerationNode:
    def __init__(self):
        self.length = None
        self.code = None

    def list(self, state):
        yield NotImplementedError()

    # def evaluate_length(self, state):
    #     if self.length is None:
    #         self.length = self._evaluate_length(state)
    #     return self.length

    # def evaluate_code(self, state):
    #     if self.code is None:
    #         self.code = self._evaluate_code(state)
    #         if self.length is None:
    #             self.length = len(self.code)
    #         else:
    #             assert self.length == len(self.code)
    #     return self.code


    # def evaluate_from_top(self):
    #     if self.code is not None:
    #         # This node is already evaluated
    #         return self.code
    #     elif self.parent is None:
    #         # Can evaluate as-is
    #         return self.evaluate()
    #     elif self.parent.children is not None:
    #         # The parent is already unfolded, which means 
    #         assert self.parent.code is None
    #         for child in self.parent.children:
    #             if child is self:
    #                 break
    #     if self.parent is None or self.parent:
    #         self.evaluate()


class RecursiveGenerationNode(GenerationNode):
    def __init__(self):
        super().__init__()
        self.children = None

    def list(self, state):
        for child in self.unfold(state):
            yield from child.list(state)

    def unfold(self, state):
        raise NotImplementedError()

    # def _evaluate_length(self, state):
    #     if self.children is None:
    #         self.children = self.unfold(state)
    #     return sum(child.evaluate_length(state) for child in self.children)

    # def _evaluate_code(self, state):
    #     if self.children is None:
    #         self.children = self.unfold(state)
    #     return b"".join(child.evaluate_code(state) for child in self.children)


class DumbRecursiveGenerationNode(RecursiveGenerationNode):
    def __init__(self, children, state_update=None):
        super().__init__()
        self.__children = list(children)
        self.__state_update = state_update or {}

    def unfold(self, state):
        return self.__children

    # def _evaluate_length(self, state):
    #     return super()._evaluate_length({**state, **self.__state_update})

    # def _evaluate_code(self, state):
    #     return super()._evaluate_code({**state, **self.__state_update})


class LeafGenerationNode(GenerationNode):
    def __init__(self, length, body):
        super().__init__()
        self.__length = length
        self.__body = body

    def list(self, state):
        yield self

    def get_length(self, state):
        if self.__length is None:
            return len(self.get_code(state))
        if callable(self.__length):
            self.__length = self.__length(state)
        return self.__length

    def get_code(self, state):
        if callable(self.__body):
            self.__body = self.__body(state)
            self.__length = len(self.__body)
        return self.__body
