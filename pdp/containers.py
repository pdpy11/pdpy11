class CaseInsensitiveDict:
    def __init__(self, container=None, **kwargs):
        if container:
            assert not kwargs
            self.container = {key.lower(): (key, value) for key, value in container.items()}
        elif kwargs:
            self.container = {key.lower(): (key, value) for key, value in kwargs.items()}
        else:
            self.container = {}


    def __contains__(self, key):
        return key.lower() in self.container


    def __getitem__(self, key):
        try:
            return self.container[key.lower()][1]
        except KeyError:
            raise KeyError(key) from None


    def __setitem__(self, key, value):
        self.container[key.lower()] = (key, value)


    def items(self):
        return self.container.values()
