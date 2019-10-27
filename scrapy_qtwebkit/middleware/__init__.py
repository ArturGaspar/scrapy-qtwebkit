"""Scrapy side."""

import atexit
import logging
import sys
from functools import partial

from scrapy.exceptions import NotConfigured, NotSupported
from scrapy.http import HtmlResponse, Request
from scrapy.selector import Selector

from twisted.internet import reactor
from twisted.internet.defer import (DeferredLock, DeferredSemaphore,
                                    inlineCallbacks)
from twisted.internet.endpoints import ProcessEndpoint, clientFromString
from twisted.internet.error import ConnectionLost
from twisted.python.failure import Failure
from twisted.spread import jelly, pb

from .._intermediaries import RequestFromScrapy, ScrapyNotSupported
from .cookies import RemotelyAccessbileCookiesMiddleware
from .downloader import BrowserRequestDownloader
from .utils import (DummySemaphore, PBBrokerForEndpoint,
                    PBReferenceMethodsWrapper)


__all__ = ['BrowserMiddleware']


logger = logging.getLogger(__name__)


class BrowserRequest(Request):
    """

    A request to be handled by the browser. May be provided either an URL to
    open a new webpage for, or an existing webpage object to continue
    processing in the callback.

    The latter option is useful for producing items or requests, while keeping
    the page open for further processing.

    """

    _engine = None

    def __init__(self, url=None, webpage=None, *args, **kwargs):
        if webpage:
            if url:
                raise TypeError("must not provide both url and webpage")
            url = "about:blank"
        elif not url:
            raise TypeError("must provide either url or webpage")
        self.webpage = webpage
        # kwargs.setdefault('dont_filter', True)
        self.actual_requests = 0
        super().__init__(url, *args, **kwargs)

    def __repr__(self):
        return ("<Browser {} page {} (with {} requests)>"
                ).format(self._engine, self.url, self.actual_requests)

    def __str__(self):
        return repr(self)

    def replace(self, *args, **kwargs):
        webpage = kwargs.setdefault('webpage', self.webpage)
        if webpage is not None:
            kwargs['url'] = None

        return super().replace(*args, **kwargs)


class _RequestCountRemoteIncreaser(pb.Referenceable):
    def __init__(self, request):
        super().__init__()
        self._browser_request = request

    def remote_increase_request_count(self, num_requests=1):
        self._browser_request.actual_requests += num_requests


class BrowserResponse(HtmlResponse):
    @inlineCallbacks
    def update_body(self):
        encoding, body = yield self.webpage.callRemote('get_body')
        self._cached_benc = None
        self._cached_ubody = None
        self._cached_selector = None
        self._encoding = encoding
        self._set_body(body)

    def close_webpage(self):
        self.webpage = None


class BrowserMiddleware(object):
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings

        if crawler.settings.getbool('BROWSER_ENGINE_COOKIES_ENABLED', False):
            if crawler.settings.getbool('COOKIES_ENABLED'):
                logger.warning("Default cookies middleware enabled together "
                               "with browser engine aware cookies middleware. "
                               "Set COOKIES_ENABLED to False.")
            cookies_mw = RemotelyAccessbileCookiesMiddleware(
                debug=crawler.settings.getbool('COOKIES_DEBUG')
            )
        else:
            cookies_mw = None

        server = settings.get('BROWSER_ENGINE_SERVER')
        if server:
            endpoint = clientFromString(reactor, server)
        else:
            if settings.getbool('BROWSER_ENGINE_START_SERVER', False):
                # Twisted logs the process's stderr with INFO level.
                logging.getLogger("twisted").setLevel(logging.INFO)
                argv = [sys.executable, "-m",
                        "scrapy_qtwebkit.browser_engine", "stdio"]
                endpoint = ProcessEndpoint(reactor, argv[0], argv, env=None)
            else:
                raise NotConfigured("Must provide either BROWSER_ENGINE_SERVER "
                                    "or BROWSER_ENGINE_START_SERVER")

        ext = cls(
            crawler,
            endpoint,
            page_limit=settings.getint('BROWSER_ENGINE_PAGE_LIMIT', 4),
            browser_options=settings.getdict('BROWSER_ENGINE_OPTIONS'),
            cookies_middleware=cookies_mw,
        )

        return ext

    def __init__(self, crawler, client_endpoint, page_limit=4,
                 browser_options=None, cookies_middleware=None):
        super().__init__()
        self._crawler = crawler
        self._client_endpoint = client_endpoint
        if page_limit:
            self._semaphore = DeferredSemaphore(page_limit)
        else:
            self._semaphore = DummySemaphore()

        self.browser_options = (browser_options or {})
        self.cookies_mw = cookies_middleware

        self._downloader = None
        self._browser = None
        self._browser_init_lock = DeferredLock()

    @inlineCallbacks
    def _init_browser(self):
        # XXX: open at most one browser at a time per client (i.e. per Scrapy
        #      instance), ensure there is no communication between pages of a
        #      browser. If not possible, open one browser per cookiejar but also
        #      allow the user to have separate browsers on the same cookiejar.

        if self._browser is not None:
            return

        factory = pb.PBClientFactory(security=jelly.DummySecurityOptions())
        factory.protocol = PBBrokerForEndpoint
        broker = yield self._client_endpoint.connect(factory)
        if isinstance(self._client_endpoint, ProcessEndpoint):
            atexit.register(broker.transport.signalProcess, "TERM")

        if self._downloader is None:
            self._downloader = BrowserRequestDownloader(self._crawler)

        root = yield factory.getRootObject()
        self._browser = yield root.callRemote('open_browser',
                                              downloader=self._downloader,
                                              options=self.browser_options)

    @inlineCallbacks
    def _get_browser(self):
        if self._browser is None:
            yield self._browser_init_lock.run(self._init_browser)

        return self._browser

    @inlineCallbacks
    def process_request(self, request, spider):
        if self.cookies_mw:
            yield self.cookies_mw.process_request(request, spider)

        if isinstance(request, BrowserRequest):
            response = yield self._make_browser_request(request, spider)
            return response

    def process_response(self, request, response, spider):
        if self.cookies_mw:
            return self.cookies_mw.process_response(request, response, spider)
        else:
            return response

    @inlineCallbacks
    def _make_browser_request(self, request, spider):
        browser = yield self._get_browser()

        webpage_options = {
            'count_increaser': _RequestCountRemoteIncreaser(request),
            'user_agent': request.headers.get('User-Agent')
        }
        if self.cookies_mw and 'dont_merge_cookies' not in request.meta:
            cookiejarkey = request.meta.get("cookiejar")
            cookiejar = self.cookies_mw.jars[cookiejarkey].jar
            webpage_options['cookiejarkey'] = cookiejarkey
            webpage_options['cookiejar'] = cookiejar

        yield self._semaphore.acquire()
        try:
            webpage = yield browser.callRemote('create_webpage',
                                               webpage_options)
        except:
            self._semaphore.release()
            raise
        else:
            weakref.finalize(webpage, self._semaphore.release)

        result = webpage.callRemote('load_request',
                                    RequestFromScrapy(request.url,
                                                      request.method,
                                                      request.headers,
                                                      request.body))
        result.addCallback(partial(self._handle_page_load, request, webpage))
        del webpage
        return (yield result)

    @inlineCallbacks
    def _handle_page_load(self, request, webpage,
                          load_result=(True, 200, None, None)):
        """

        Handle a request for a web page, either a page load or a request to
        continue using an existing page object.

        """

        browser_response = request.meta.get('browser_response', False)

        try:
            ok, status, headers, exc = load_result

            if ok:
                if browser_response:
                    respcls = BrowserResponse
                else:
                    respcls = HtmlResponse

                url = yield webpage.callRemote('get_url')
                encoding, body = yield webpage.callRemote('get_body')
                response = respcls(status=status,
                                   url=url,
                                   headers=headers,
                                   body=body,
                                   encoding=encoding,
                                   request=request)

                if browser_response:
                    response.webpage = PBReferenceMethodsWrapper(webpage)

            else:
                if isinstance(exc, ScrapyNotSupported):
                    exc = NotSupported(*exc.args)
                raise exc

        except Exception as err:
            response = Failure(err)
        finally:
            # There should be one reference from this same scope, plus, in case
            # it was set, one from the response (actually from the
            # PBReferenceMethodsWrapper).
            expected_refcount = 1
            if browser_response:
                expected_refcount += 1
            refcount = sys.getrefcount(webpage) - 1
            if refcount != expected_refcount:
                logger.error(f"Expected {expected_refcount} references to "
                             f"{webpage!r} but found {refcount}:\n"
                             "\n".join(map(repr, gc.get_referrers(webpage))))
            del webpage

        return response
