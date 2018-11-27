"""Scrapy side."""

from functools import partial

from scrapy.exceptions import NotSupported
from scrapy.http import HtmlResponse, Request

from twisted.internet import reactor
from twisted.internet.defer import DeferredLock, inlineCallbacks
from twisted.python.failure import Failure
from twisted.spread import jelly, pb

from .._intermediaries import RequestFromScrapy, ScrapyNotSupported
from .cookies import RemotelyAccessbileCookiesMiddleware
from .downloader import BrowserRequestDownloader
from .utils import PbReferenceMethodsWrapper


__all__ = ['BrowserMiddleware']


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


class BrowserMiddleware(object):
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings

        if crawler.settings.getbool('BROWSER_COOKIES_ENABLED', False):
            cookies_middleware = RemotelyAccessbileCookiesMiddleware(
                crawler.settings.getbool('COOKIES_DEBUG')
            )
        else:
            cookies_middleware = None

        ext = cls(
            crawler,
            page_limit=settings.getint("BROWSER_PAGE_LIMIT", 4),
            cookies_middleware=cookies_middleware
        )

        return ext

    def __init__(self, crawler, page_limit=4, cookies_middleware=None):
        super().__init__()
        self._crawler = crawler
        self.page_limit = page_limit
        self.cookies_middleware = cookies_middleware

        self._pb_client = None
        self._downloader = None
        self._browser = None
        self._browser_init_lock = DeferredLock()

    @inlineCallbacks
    def _init_browser(self):
        # XXX: open at most one browser at a time per client (i.e. per Scrapy
        #      instance), ensure there is no communication between pages of a
        #      browser. If not possible, open one browser per cookiejar but also
        #      allow the user to have separate browsers on the same cookiejar.

        if self._browser is None:
            if self._pb_client is None:
                self._pb_client = pb.PBClientFactory(
                    security=jelly.DummySecurityOptions()
                )
                reactor.connectTCP("localhost", 8789, self._pb_client)

            if self._downloader is None:
                self._downloader = BrowserRequestDownloader(self._crawler)

            browser_manager = yield self._pb_client.getRootObject()
            self._browser = yield browser_manager.callRemote('open_browser',
                                                             self._downloader)

    @inlineCallbacks
    def _get_browser(self):
        if self._browser is None:
            yield self._browser_init_lock.run(self._init_browser)

        return self._browser

    @inlineCallbacks
    def process_request(self, request, spider):
        if self.cookies_middleware:
            yield self.cookies_middleware.process_request(request, spider)

        if isinstance(request, BrowserRequest):
            response_dfd = self._make_browser_request(request, spider)
            return (yield response_dfd)

    def process_response(self, request, response, spider):
        if self.cookies_middleware:
            return self.cookies_middleware.process_response(request, response,
                                                            spider)
        else:
            return response

    @inlineCallbacks
    def _make_browser_request(self, request, spider):
        browser = yield self._get_browser()

        webpage_options = {
            'count_increaser': _RequestCountRemoteIncreaser(request),
            'user_agent': request.headers.get('User-Agent')
        }
        if self.cookies_middleware and 'dont_merge_cookies' not in request.meta:
            cookiejarkey = request.meta.get("cookiejar")
            cookiejar = self.cookies_middleware.jars[cookiejarkey].jar
            webpage_options['cookiejarkey'] = cookiejarkey
            webpage_options['cookiejar'] = cookiejar

        webpage = yield browser.callRemote('create_webpage', webpage_options)

        result = webpage.callRemote('load_request',
                                    RequestFromScrapy(request.url,
                                                      request.method,
                                                      dict(request.headers),
                                                      request.body))
        result.addCallback(partial(self._handle_page_load, request, webpage))
        return (yield result)

    @inlineCallbacks
    def _handle_page_load(self, request, webpage,
                          load_result=(True, 200, None, None)):
        """

        Handle a request for a web page, either a page load or a request to
        continue using an existing page object.

        """

        try:
            ok, status, headers, exc = load_result

            if ok:
                url = yield webpage.callRemote('get_url')

                browser_response = request.meta.get('browser_response', False)
                if browser_response:
                    respcls = BrowserResponse
                else:
                    respcls = HtmlResponse

                encoding, body = yield webpage.callRemote('get_body')
                response = respcls(status=status,
                                   url=url,
                                   headers=headers,
                                   body=body,
                                   encoding=encoding,
                                   request=request)

                if browser_response:
                    response.webpage = PbReferenceMethodsWrapper(webpage)

            else:
                if isinstance(exc, ScrapyNotSupported):
                    exc = NotSupported(*exc.args)
                raise exc

        except Exception as err:
            response = Failure(err)

        return response
