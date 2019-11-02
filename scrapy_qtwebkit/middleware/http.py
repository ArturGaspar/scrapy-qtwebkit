from scrapy.http import HtmlResponse, Request
from twisted.internet.defer import inlineCallbacks
from twisted.spread import pb


class _RemoteRequestCounter(pb.Referenceable):
    def __init__(self, request):
        super().__init__()
        self._browser_request = request

    def remote_increase_request_count(self, num_requests=1):
        self._browser_request.actual_requests += num_requests


class BrowserRequest(Request):
    """

    A request to be handled by the browser.

    """

    def __init__(self, *args, **kwargs):
        # kwargs.setdefault('dont_filter', True)
        super().__init__(*args, **kwargs)
        self.actual_requests = 0
        self.remote_counter = _RemoteRequestCounter(self)

    def __repr__(self):
        return ("<Browser page {} (with {} requests)>"
                ).format(self.url, self.actual_requests)

    def __str__(self):
        return repr(self)


class BrowserResponse(HtmlResponse):
    @inlineCallbacks
    def update_body(self):
        encoding, body = yield self.webpage.callRemote('get_body')
        self._cached_benc = None
        self._cached_ubody = None
        self._cached_selector = None
        self._encoding = encoding
        self._set_body(body)

    @property
    def webpage(self):
        if self._webpage is None:
            raise ValueError("cannot access response webpage after closing")
        return self._webpage

    def close_webpage(self):
        if self._webpage:
            dfd_close = self._webpage.callRemote('close')
            self._webpage = None

            semaphore = self._semaphore
            self._semaphore = None
            if semaphore:
                def semaphore_release(v):
                    semaphore.release()
                    return v

                dfd_close.addBoth(semaphore_release)

            return dfd_close

    def __del__(self):
        self.close_webpage()
