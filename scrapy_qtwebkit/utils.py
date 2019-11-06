from twisted.internet.defer import Deferred, DeferredList


class PendingDeferreds(object):
    def __init__(self, dfds=None):
        super().__init__()
        self._dfds = set()
        if dfds:
            for dfd in dfds:
                self.add(dfd)

    def add(self, dfd):
        if not isinstance(dfd, Deferred):
            return
        self._dfds.add(dfd)
        return dfd.addBoth(self._callback, dfd)

    def _callback(self, result, dfd):
        self._dfds.remove(dfd)
        return result

    def deferred(self):
        return DeferredList(self._dfds).addCallback(lambda results: None)
