import json
import logging
import time

from twisted.internet import reactor
from twisted.internet.defer import (Deferred, inlineCallbacks, maybeDeferred,
                                    returnValue)

from .qt.QtWebKit import QWebElement, QWebElementCollection


logger = logging.getLogger()


def deferred_for_signal(signal):
    d = Deferred()

    def callback(*args):
        signal.disconnect(callback)
        d.callback(args)

    signal.connect(callback)

    return d


_mouse_event_script = """
    (function(element) {{
        var event = document.createEvent('MouseEvents');
        event.initEvent({}, true, true);
        element.dispatchEvent(event);
    }})(this);
"""

def mouse_event(element, event):
    element.evaluateJavaScript(_mouse_event_script.format(json.dumps(event)))


class ElementDidNotAppear(Exception):
    pass


@inlineCallbacks
def wait_for_element(func, *args, **kwargs):
    interval = kwargs.pop('interval', 1)
    timeout = kwargs.pop('timeout', 30)
    log = kwargs.pop('log', logger.debug)

    description = kwargs.pop('description', None)
    if description is None:
        args_repr = ", ".join(list(map(repr, args)) +
                              [k + "=" + repr(v) for k, v in kwargs.items()])
        description = getattr(func, '__name__', "") + "(" + args_repr + ")"

    start = time.time()

    while timeout is None or (time.time() - start) <= timeout:
        log("Waiting for element {}".format(description))
        el = yield maybeDeferred(func, *args, **kwargs)
        if isinstance(el, QWebElement):
            if not el.isNull():
                returnValue(el)
        elif isinstance(el, QWebElementCollection):
            if el.count():
                returnValue(el.toList())
        elif el is not None:
            raise TypeError("{} returned {!r} of type {}".format(description,
                                                                 el, type(el)))

        d = Deferred()
        reactor.callLater(interval, d.callback, None)
        yield d

    raise ElementDidNotAppear(("element {} did not appear on page"
                               ).format(description))


def iter_child_elements(element):
    child = element.firstChild()
    while not child.isNull():
        yield child
        child = child.nextSibling()
