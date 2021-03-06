import logging
import weakref
from collections.abc import Collection, Mapping

from scrapy import Request, signals

from ..utils import PendingDeferreds

from .http import BrowserResponse


logger = logging.getLogger(__name__)


class DefaultWeakKeyDict(weakref.WeakKeyDictionary):
    def __init__(self, constructor):
        super().__init__()
        self._constructor = constructor

    def __getitem__(self, key):
        if key not in self:
            self[key] = self._constructor()
        return super().__getitem__(key)


class BrowserResponseTrackerMiddleware(object):
    """

    Tracks if browser responses are kept by the user in subsequent requests,
    and closes them when not.

    """

    # Weak references are used so as not to keep a browser page open if the
    # user deletes the response before returning from the callback.

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls()
        crawler.signals.connect(mw._spider_closed,
                                signal=signals.spider_closed)
        return mw

    def __init__(self):
        super().__init__()
        self._responses_with_user = DefaultWeakKeyDict(int)
        self._responses_with_scrapy = DefaultWeakKeyDict(int)
        self._pending_close_requests = PendingDeferreds()

    def _spider_closed(self):
        return self._pending_close_requests.deferred()

    def _get_browser_responses(self, values, seen_objects=()):
        seen_objects += (values,)
        if isinstance(values, Mapping):
            values = list(values.values())
        for value in values:
            if isinstance(value, BrowserResponse):
                yield value
            elif isinstance(value, Collection):
                if value in seen_objects:
                    continue
                yield from self._get_browser_responses(value, seen_objects)

    def process_spider_output(self, response, result, spider):
        if not response.meta.get('browser_response_track_active', True):
            yield from result
            return

        in_responses = weakref.WeakSet()
        if isinstance(response, BrowserResponse):
            # Add 1 when the response is sent from Scrapy (expected to happen
            # once, at the first time the response is seen).
            # If it is not given to Scrapy (e.g. in request meta) by the user,
            # it will go back to 0; otherwise, it will stay at +1, but will go
            # to 0 once the user receives it again and does not send it back.
            self._responses_with_scrapy[response] += 1
            in_responses.add(response)
        in_responses.update(self._get_browser_responses(response.meta))
        del response

        for response in in_responses:
            self._responses_with_scrapy[response] -= 1
            self._responses_with_user[response] += 1
            del response

        for r in result:
            if isinstance(r, Request):
                out_responses = weakref.WeakSet(
                    self._get_browser_responses(r.meta)
                )
                for response in out_responses:
                    self._responses_with_scrapy[response] += 1
                    del response
            yield r
            del r

        for response in in_responses:
            self._responses_with_user[response] -= 1
            del response

        for response in (weakref.WeakSet(self._responses_with_user.keys()) |
                         weakref.WeakSet(self._responses_with_scrapy.keys())):
            scrapy_count = self._responses_with_scrapy[response]
            user_count = self._responses_with_user[response]
            if (scrapy_count + user_count) == 0:
                logger.info(f"Closing webpage in response {response!r}")
                self._pending_close_requests.add(response.close_webpage())
            else:
                logger.debug(f"Not closing webpage in response {response!r}, "
                             f"held by Scrapy {scrapy_count} times and by user "
                             f"{user_count} times")
            del response
