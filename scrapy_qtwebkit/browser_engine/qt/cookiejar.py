import datetime
from http.cookiejar import Absent, Cookie

from PyQt5.QtCore import QDateTime
from PyQt5.QtNetwork import QNetworkCookie, QNetworkCookieJar

from .._cookies_for_url import cookies_for_url


class CookielibQtCookieJar(QNetworkCookieJar):
    """Qt cookie jar for accessing Python cookielib cookies."""

    def __init__(self, cookiejar, parent=None):
        super().__init__(parent)
        self._jar = cookiejar

    @staticmethod
    def _make_qt_cookie(cookie):
        """Build a QNetworkCookie object from a cookielib.Cookie object."""
        qt_cookie = QNetworkCookie(cookie.name.encode(), cookie.value.encode())
        qt_cookie.setDomain(cookie.domain)
        if cookie.expires is not None:
            qt_cookie.setExpirationDate(QDateTime.fromTime_t(cookie.expires))
        qt_cookie.setHttpOnly(bool(cookie.get_nonstandard_attr("HttpOnly")))
        qt_cookie.setPath(cookie.path)
        qt_cookie.setSecure(cookie.secure)
        return qt_cookie

    @staticmethod
    def _make_cookielib_cookie(qt_cookie):
        """Build a cookielib.Cookie object from a QNetworkCookie object."""
        # TODO: port number
        # TODO: bytes or text

        absent_if_none = lambda v: v if v is not None else Absent

        domain = absent_if_none(qt_cookie.domain())
        domain_specified = domain is not Absent
        domain_initial_dot = domain_specified and domain.startswith('.')

        path = absent_if_none(qt_cookie.path())
        path_specified = path is not Absent

        qdate = qt_cookie.expirationDate()
        if qdate:
            expires = qt_cookie.expirationDate().toTime_t()
            discard = False
        else:
            expires = None
            discard = True

        return Cookie(
            version=0,
            name=bytes(qt_cookie.name()).decode(),
            value=bytes(qt_cookie.value()).decode(),
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=domain_specified,
            domain_initial_dot=domain_initial_dot,
            path=path,
            path_specified=path_specified,
            secure=qt_cookie.isSecure(),
            expires=expires,
            discard=discard,
            comment=None,
            comment_url=None,
            rest={'HttpOnly': qt_cookie.isHttpOnly()}
        )

    def _cookies_for_url(self, url):
        return cookies_for_url(self._jar, url)

    def cookiesForUrl(self, qurl):
        return list(map(self._make_qt_cookie,
                        self._cookies_for_url(qurl.toString())))

    def deleteCookie(self, qt_cookie):
        domain = qt_cookie.domain()
        path = qt_cookie.path()
        name = bytes(qt_cookie.name())
        try:
            self._jar.clear(domain, path, name)
        except KeyError:
            return False
        else:
            return True

    def insertCookie(self, qt_cookie):
        expdate = qt_cookie.expirationDate()
        if expdate:
            expiration_date = expdate.toPyDateTime()
            is_deletion = ((not qt_cookie.isSessionCookie()) and
                           expdate.toPyDateTime() < datetime.datetime.now())
        else:
            is_deletion = False

        if is_deletion:
            self.deleteCookie(qt_cookie)
            return False
        else:
            cookie = self._make_cookielib_cookie(qt_cookie)
            # XXX: what
            # perhaps expiration?
            if cookie is not None:
                self._jar.set_cookie(cookie)
                return True
            else:
                self.deleteCookie(qt_cookie)
                return False
