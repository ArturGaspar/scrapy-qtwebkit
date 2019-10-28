"""Scrapy side."""

import atexit
import logging
import sys
import weakref
from functools import partial

from scrapy.exceptions import NotConfigured, NotSupported

from twisted.internet import reactor
from twisted.internet.defer import (DeferredLock, DeferredSemaphore,
                                    inlineCallbacks)
from twisted.internet.endpoints import ProcessEndpoint, clientFromString
from twisted.python.failure import Failure
from twisted.spread import jelly, pb

from .._intermediaries import RequestFromScrapy, ScrapyNotSupported
from .cookies import RemotelyAccessbileCookiesMiddleware
from .downloader import BrowserRequestDownloader
from .http import BrowserRequest, BrowserResponse
from .spidermw import BrowserResponseTrackerMiddleware
from .utils import (DummySemaphore, PBBrokerForEndpoint,
                    PBReferenceMethodsWrapper)


__all__ = ['BrowserMiddleware', 'BrowserRequest',
           'BrowserResponseTrackerMiddleware']


logger = logging.getLogger(__name__)


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

        options = {
            'remote_request_counter': request.remote_counter,
            'user_agent': request.headers.get('User-Agent')
        }
        if self.cookies_mw and 'dont_merge_cookies' not in request.meta:
            cookiejarkey = request.meta.get("cookiejar")
            cookiejar = self.cookies_mw.jars[cookiejarkey].jar
            options['cookiejarkey'] = cookiejarkey
            options['cookiejar'] = cookiejar

        yield self._semaphore.acquire()
        try:
            webpage = yield browser.callRemote('create_webpage', options)
        except:
            self._semaphore.release()
            raise

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
                    response._webpage = PBReferenceMethodsWrapper(webpage)
                    response._semaphore = self._semaphore

            else:
                if isinstance(exc, ScrapyNotSupported):
                    exc = NotSupported(*exc.args)
                raise exc

        except Exception as err:
            response = Failure(err)

        if not browser_response:
            try:
                yield webpage.callRemote('close')
            finally:
                self._semaphore.release()

        return response
