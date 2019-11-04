from twisted.internet.defer import succeed
from twisted.spread import pb


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


# Endpoints do not call ClientFactory.clientConnectionLost(), so do it here.
class PBBrokerForEndpoint(pb.Broker):
    def connectionLost(self, reason):
        super().connectionLost(reason)
        self.factory.clientConnectionLost(None, reason)

    def connectionFailed(self):
        super().connectionFailed()
        self.factory.clientConnectionFailed(None, None)


class DummySemaphore(object):
    tokens = 1

    def acquire(self):
        return succeed(self)

    def release(self):
        pass
