from http.cookiejar import Cookie, CookieJar

from twisted.spread import pb


class CopyableCookie(Cookie, pb.Copyable, pb.RemoteCopy, object):
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


class _CookieJarRemoteMethodCaller(pb.Referenceable, object):
    def __init__(self, cookiejar):
        super().__init__()
        self._cookiejar = cookiejar

    def remote_set_cookie(self, changer_id, cookie):
        self._cookiejar.set_cookie(cookie, changer_id=changer_id)

    def remote_delete_cookie(self, changer_id, domain, path, name):
        self._cookiejar.clear(domain, path, name, change_id=changer_id)


class RemotelyAccessbileCookieJar(CookieJar, pb.Cacheable, object):
    def __init__(self, policy=None):
        super().__init__(policy=policy)
        self._remote_method_caller = _CookieJarRemoteMethodCaller(self)
        self._observers = []
        self._last_changer = {}

    def set_cookie(self, cookie, changer_id=None):
        if not isinstance(cookie, CopyableCookie):
            cookie = CopyableCookie.from_regular_cookie(cookie)
        super().set_cookie(cookie)
        self._notify_observers((cookie.domain, cookie.path, cookie.name),
                               changer_id, 'set_cookie', cookie)

    def clear(self, domain, path, name, changer_id=None):
        if domain is None or path is None or name is None:
            raise ValueError("domain, path and name must be given")
        super().clear(domain, path, name)
        self._notify_observers((domain, path, name), changer_id,
                               'delete_cookie', domain, path, name)

    def _notify_observers(self, key, changer_id, method, *args):
        # Observers record their own changes when sending them to the master,
        # avoiding the need to communicate a change to the observer that made
        # it.

        # If another observer previously made a change to the key which this
        # observer is changing now, the change made by the former may have
        # reached the latter after it recorded its own change. Thus, in this
        # case, the observer making the change now must also be notified.
        is_same_changer = (changer_id is not None and
                           self._last_changer.get(key) == changer_id)

        self._last_changer[key] = changer_id

        for o in self._observers:
            if is_same_changer and changer_id == hash(o):
                continue
            o.callRemote(method, *args)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self._observers.append(observer)
        return self._cookies, self._remote_method_caller, hash(observer)

    def stoppedObserving(self, perspective, observer):
        self._observers.remove(observer)


class RemoteCookieJar(CookieJar, pb.RemoteCache, object):
    def setCopyableState(self, state):
        self._cookies, self._jarmethods, self._observer_id = state

    def observe_set_cookie(self, cookie):
        super().set_cookie(cookie)

    def observe_delete_cookie(self, domain, path, name):
        super().clear(domain, path, name)

    def set_cookie(self, cookie):
        if not isinstance(cookie, CopyableCookie):
            cookie = CopyableCookie.from_regular_cookie(cookie)
        self._jarmethods.callRemote('set_cookie', self._observer_id, cookie)
        self.observe_set_cookie(cookie)

    def clear(self, domain, path, name):
        if domain is None or path is None or name is None:
            raise ValueError("domain, path and name must be given")
        self._jarmethods.callRemote('delete_cookie', self._observer_id,
                                    domain, path, name)
        self.observe_delete_cookie(domain, path, name)
