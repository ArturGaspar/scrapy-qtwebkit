from collections import defaultdict

from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.http.cookies import CookieJar as CookieJarWrapper
from twisted.internet.defer import inlineCallbacks

from ..cookies import RemotelyAccessibleCookieJar


class _DummyLock(object):
    def acquire(self):
        pass

    def release(self):
        pass


class RemotelyAccessibleCookieJarWrapper(CookieJarWrapper):
    def __init__(self, policy=None, check_expired_frequency=10000):
        super().__init__(policy, check_expired_frequency)
        self.jar = RemotelyAccessibleCookieJar(self.policy)
        self.jar._cookies_lock = _DummyLock()


class RemotelyAccessibleCookiesMiddleware(CookiesMiddleware):
    def __init__(self, debug=False):
        super().__init__(debug)
        self.jars = defaultdict(RemotelyAccessibleCookieJarWrapper)


@inlineCallbacks
def sync_cookies(cookiejar, webpage):
    # Sync and commit cookie updates from browser engine first, so that
    # they prevail over cookie updates from the Scrapy side.
    yield webpage.callRemote('_sync_cookies')
    cookiejar.commit()

    yield cookiejar.sync()
    yield webpage.callRemote('_commit_cookies')
