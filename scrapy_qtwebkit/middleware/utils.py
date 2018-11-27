class PbReferenceMethodsWrapper(object):
    def __init__(self, reference):
        super().__init__()
        self._pb_reference = reference

    def __getattr__(self, attr):
        try:
            return getattr(self._pb_reference, attr)
        except AttributeError:
            return self._pb_reference.remoteMethod(attr)
