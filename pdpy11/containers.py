class CaseInsensitiveDict:
    def __init__(self, container=None):
        if container:
            self.container = {key.lower(): (key, value) for key, value in container.items()}
        else:
            self.container = {}


    def __contains__(self, key):
        return isinstance(key, str) and key.lower() in self.container


    def __getitem__(self, key):
        try:
            return self.container[key.lower()][1]
        except KeyError:
            raise KeyError(key) from None


    def __setitem__(self, key, value):
        self.container[key.lower()] = (key, value)


    def items(self):
        return self.container.values()


    def __iter__(self):
        for key, _value in self.container.values():
            yield key


    def get(self, key, default=None):
        return self.container.get(key.lower(), (None, default))[1]
