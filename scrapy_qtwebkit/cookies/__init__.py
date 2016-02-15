import datetime
from cookielib import Absent

from PyQt5.QtCore import QDateTime
from PyQt5.QtNetwork import QNetworkCookie, QNetworkCookieJar

from ._cookies_for_url import cookies_for_url


class ScrapyAwareCookieJar(QNetworkCookieJar):
    """Qt cookie jar for accessing Scrapy cookies."""

    def __init__(self, cookies_middleware, cookiejarkey, parent=None):
        super(ScrapyAwareCookieJar, self).__init__(parent)
        self.cookies_middleware = cookies_middleware
        self.cookiejarkey = cookiejarkey

    @property
    def _jar(self):
        return self.cookies_middleware.jars[self.cookiejarkey]

    @staticmethod
    def _make_qt_cookie(cookie):
        """Build a QNetworkCookie object from a cookielib.Cookie object."""

        qt_cookie = QNetworkCookie(cookie.name, cookie.value)
        qt_cookie.setDomain(cookie.domain)
        if cookie.expires is not None:
            qt_cookie.setExpirationDate(QDateTime.fromTime_t(cookie.expires))
        qt_cookie.setHttpOnly(bool(cookie.get_nonstandard_attr("HttpOnly")))
        qt_cookie.setPath(cookie.path)
        qt_cookie.setSecure(cookie.secure)
        return qt_cookie

    def _make_cookielib_cookie(self, qt_cookie):
        """Build a cookielib.Cookie object from a QNetworkCookie object."""
        return self._jar.jar._cookie_from_cookie_tuple((
            bytes(qt_cookie.name()),
            bytes(qt_cookie.value()),
            {
                'domain': qt_cookie.domain(),
                'path': qt_cookie.path(),
                'expires': (qt_cookie.expirationDate().toTime_t()
                            if not qt_cookie.expirationDate().isNull()
                            else Absent),
                'secure': qt_cookie.isSecure()
            },
            {'HttpOnly': qt_cookie.isHttpOnly()}
        ), None)

    def _cookies_for_url(self, url):
        """Get cookies (as cookielib.Cookie objects) for an URL."""
        return cookies_for_url(self._jar.jar, url)

    def cookiesForUrl(self, qurl):
        self._jar.jar.clear_expired_cookies()
        return list(map(self._make_qt_cookie,
                        self._cookies_for_url(qurl.toString())))

    def deleteCookie(self, qt_cookie):
        domain = qt_cookie.domain()
        path = qt_cookie.path()
        name = bytes(qt_cookie.name())
        try:
            self._jar.jar.clear(domain, path, name)
        except KeyError:
            return False
        else:
            return True

    def insertCookie(self, qt_cookie):
        expiration_date = qt_cookie.expirationDate().toPyDateTime()
        is_deletion = ((not qt_cookie.isSessionCookie()) and
                       expiration_date < datetime.datetime.now())

        if is_deletion:
            self.deleteCookie(qt_cookie)
            return False
        else:
            cookie = self._make_cookielib_cookie(qt_cookie)
            if cookie is not None:
                self._jar.set_cookie(self._make_cookielib_cookie(qt_cookie))
                return True
            else:
                self.deleteCookie(qt_cookie)
                return False
