import logging
from http.cookiejar import Cookie, CookieJar
from operator import methodcaller

from twisted.internet.defer import DeferredList
from twisted.spread import pb

from .utils import PendingDeferreds


logger = logging.getLogger(__name__)


class CopyableCookie(Cookie, pb.Copyable, pb.RemoteCopy):
    @classmethod
    def from_regular_cookie(cls, cookie):
        args = {}
        for attr in ['version', 'name', 'value', 'port', 'port_specified',
                     'domain', 'domain_specified', 'domain_initial_dot',
                     'path', 'path_specified', 'secure', 'expires', 'discard',
                     'comment', 'comment_url', 'rfc2109']:
            args[attr] = getattr(cookie, attr)
        args['rest'] = cookie._rest
        return cls(**args)

    def getStateToCopy(self):
        return self.__dict__.copy()

    def setCopyableState(self, state):
        self.__dict__ = state


class _CookieJarRemoteMethodCaller(pb.Referenceable):
    def __init__(self, cookiejar):
        super().__init__()
        self._cookiejar = cookiejar

    def remote_set_cookie(self, changer_id, key, cookie):
        self._cookiejar._remote_set_cookie(key, cookie, changer_id=changer_id)

    def remote_commit(self):
        return self._cookiejar.commit()


class SynchronisedCookieJar(CookieJar):
    def __init__(self, policy=None, auto_sync=False, local_observers=None):
        super().__init__(policy=policy)
        self._remote_changes = {}
        self._pending = PendingDeferreds()
        self._auto_sync = auto_sync
        self.local_observers = local_observers or []

    def sync(self):
        """Ensure the remote copy has received all updates."""
        return self._pending.deferred()

    def commit(self):
        """Commit updates received from the remote."""
        if self._auto_sync:
            return

        result = []
        changes = list(self._remote_changes.items())
        self._remote_changes.clear()
        for key, cookie in changes:
            self._do_change(key, cookie)
            result.extend(map(methodcaller('cookie_change', key, cookie),
                              self.local_observers))
        return DeferredList(result, fireOnOneErrback=True
                            ).addCallback(lambda result: None)

    def _remote_set_cookie(self, key, cookie):
        if self._auto_sync:
            self._do_change(key, cookie)
            return DeferredList(map(methodcaller('cookie_change', key, cookie),
                                    self.local_observers),
                                fireOnOneErrback=True
                                ).addCallback(lambda result: None)
        else:
            if cookie:
                logger.debug(f"Staging cookie update: {cookie}")
            else:
                logger.debug(f"Staging cookie deletion: {key}")
            self._remote_changes[key] = cookie

    def _do_change(self, key, cookie):
        if cookie:
            logger.debug(f"Committing cookie update: {cookie}")
            super().set_cookie(cookie)
        else:
            logger.debug(f"Committing cookie deletion: {key}")
            super().clear(*key)


class RemotelyAccessibleCookieJar(SynchronisedCookieJar, pb.Cacheable):
    def __init__(self, policy=None, auto_sync=False):
        super().__init__(policy=policy, auto_sync=auto_sync)
        self._remote_method_caller = _CookieJarRemoteMethodCaller(self)
        self._observers = set()
        self._staged_last_changer = {}

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self._observers.add(observer)
        return (self._cookies, self._remote_method_caller, hash(observer),
                self._auto_sync)

    def stoppedObserving(self, perspective, observer):
        self._observers.remove(observer)

    def _cookie_change(self, key, cookie, changer_id=None):
        self._staged_last_changer[key] = changer_id
        super()._cookie_change(key, cookie)

    def _notify_observers(self, key, cookie):
        last_changer_id = self._staged_last_changer.pop(key)
        if cookie:
            logger.debug(f"Notifying cookie update: {cookie}")
        else:
            logger.debug(f"Notifying cookie deletion: {key}")
        for obs in self._observers:
            if hash(obs) == last_changer_id:
                continue
            self._pending.add(obs.callRemote('cookie_change', key, cookie))

    def _do_change(self, key, cookie):
        super()._do_change(key, cookie)
        self._notify_observers(key, cookie)

    def set_cookie(self, cookie):
        if not isinstance(cookie, CopyableCookie):
            cookie = CopyableCookie.from_regular_cookie(cookie)
        key = (cookie.domain, cookie.path, cookie.name)
        self._staged_last_changer[key] = None
        self._notify_observers(key, cookie)
        super().set_cookie(cookie)

    def clear(self, domain, path, name):
        if domain is None or path is None or name is None:
            raise ValueError("domain, path and name must be given")
        key = (domain, path, name)
        self._staged_last_changer[key] = None
        self._notify_observers(key, None)
        super().clear(domain, path, name)


class RemoteCookieJar(SynchronisedCookieJar, pb.RemoteCache):
    def setCopyableState(self, state):
        (self._cookies, self._jarmethods, self._observer_id,
         self._auto_sync) = state

    def observe_cookie_change(self, key, cookie):
        self._remote_set_cookie(key, cookie)

    def _set_remote_cookie(self, key, cookie):
        if cookie:
            logger.debug(f"Notifying cookie update: {cookie}")
        else:
            logger.debug(f"Notifying cookie deletion: {key}")
        return self._pending.add(self._jarmethods.callRemote('set_cookie',
                                                             self._observer_id,
                                                             key, cookie))

    def set_cookie(self, cookie):
        if not isinstance(cookie, CopyableCookie):
            cookie = CopyableCookie.from_regular_cookie(cookie)
        key = (cookie.domain, cookie.path, cookie.name)
        self._set_remote_cookie(key, cookie)
        super().set_cookie(cookie)

    def clear(self, domain, path, name):
        if domain is None or path is None or name is None:
            raise ValueError("domain, path and name must be given")
        key = (domain, path, name)
        self._set_remote_cookie(key, None)
        super().clear(domain, path, name)
