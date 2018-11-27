from collections import defaultdict

from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.http.cookies import CookieJar as CookieJarWrapper

from ..cookies import RemotelyAccessbileCookieJar


class _DummyLock(object):
    def acquire(self):
        pass

    def release(self):
        pass


class RemotelyAccessbileCookieJarWrapper(CookieJarWrapper):
    def __init__(self, policy=None, check_expired_frequency=10000):
        super(RemotelyAccessbileCookieJarWrapper,
              self).__init__(policy, check_expired_frequency)
        self.jar = RemotelyAccessbileCookieJar(self.policy)
        self.jar._cookies_lock = _DummyLock()


class RemotelyAccessbileCookiesMiddleware(CookiesMiddleware):
    def __init__(self, debug=False):
        super(RemotelyAccessbileCookiesMiddleware, self).__init__(debug)
        self.jars = defaultdict(RemotelyAccessbileCookieJarWrapper)
