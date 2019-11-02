from twisted.internet.defer import succeed


class PBReferenceMethodsWrapper(object):
    def __init__(self, reference):
        super().__init__()
        self._pb_reference = reference

    def __getattr__(self, attr):
        try:
            value = getattr(self._pb_reference, attr)
        except AttributeError:
            # Allows accessing remote methods by name (without remote_ prefix).
            value = self._pb_reference.remoteMethod(attr)
        return value


class DummySemaphore(object):
    tokens = 1

    def acquire(self):
        return succeed(self)

    def release(self):
        pass
