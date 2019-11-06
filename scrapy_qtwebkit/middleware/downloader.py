import logging

from scrapy import Request, signals
from scrapy.exceptions import IgnoreRequest, NotSupported
from scrapy.utils.datatypes import CaselessDict
from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectionAborted
from twisted.python.failure import Failure
from twisted.spread import pb

from .._intermediaries import (ResponseFromScrapy, ScrapyIgnoreRequest,
                               ScrapyNotSupported)


logger = logging.getLogger(__name__)


class _BrowserDownloadRequest(Request):
    def __str__(self):
        return "{} (from browser engine)".format(super().__str__())

    __repr__ = __str__


class BrowserRequestDownloader(pb.Referenceable, object):
    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self.crawler.signals.connect(self._handle_request_dropped,
                                     signals.request_dropped)

    @staticmethod
    def _handle_request_dropped(request):
        if request.meta.get('from_browser', False):
            logger.error(("Request {!r} for browser engine dropped by Scrapy "
                          "scheduler.").format(request))

    def _make_scrapy_request(self, request_from_browser, callback, errback):
        headers = CaselessDict(request_from_browser.headers)
        # Scrapy will set Content-Length if it is needed.
        headers.pop(b'Content-Length', None)

        # TODO: allow user to set a key on parent request and set it on all
        # requests from it.

        meta = {
            # XXX: could handle redirects on this side to avoid round-trips.
            'dont_redirect': True,
            'handle_httpstatus_all': True,
            'from_browser': True,
            'browser_page_first_request': request_from_browser.is_first_request,
            'dont_merge_cookies': True
        }

        # TODO: increase priority.
        return _BrowserDownloadRequest(
            url=request_from_browser.url,
            method=request_from_browser.method,
            headers=headers,
            body=request_from_browser.body,
            dont_filter=True,
            meta=meta,
            callback=callback,
            errback=errback
        )

    def remote_make_request(self, request_from_browser):
        engine = self.crawler.engine
        if not engine.running:
            raise ConnectionAborted("Scrapy engine stopping")

        spider = self.crawler.spider
        if spider not in engine.open_spiders:
            raise ConnectionAborted("Spider closed")

        dfd = Deferred()
        dfd.addCallbacks(self.process_response, self.process_failure)
        scrapy_req = self._make_scrapy_request(request_from_browser,
                                               dfd.callback, dfd.errback)
        assert scrapy_req.dont_filter
        engine.crawl(scrapy_req, spider)
        return dfd

    def process_response(self, response):
        return ResponseFromScrapy(response.url, response.status,
                                  response.headers, response.body)

    scrapy_exceptions = {IgnoreRequest: ScrapyIgnoreRequest,
                         NotSupported: ScrapyNotSupported}

    def process_failure(self, failure):
        scrapy_exc = failure.check(*self.scrapy_exceptions.keys())
        if scrapy_exc:
            new_type = self.scrapy_exceptions[scrapy_exc]
            failure = Failure(failure.value, new_type, failure.tb)

        return failure
