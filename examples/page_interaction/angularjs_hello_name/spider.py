from scrapy import Field, Item, Spider

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater

from scrapy_qtwebkit import QtWebKitRequest


class AngularJSHelloText(Item):
    text = Field()


class AngularJSHelloNameSpider(Spider):
    name = 'angularjs_hello_name'

    def start_requests(self):
        yield QtWebKitRequest("https://angularjs.org/",
                              meta={'qwebpage_response': True})

    @inlineCallbacks
    def parse(self, response):
        webpage = response.webpage
        frame = webpage.mainFrame()

        name_input = frame.findFirstElement('#the-basics + div .well input')
        name_input.setAttribute('value', "World")
        # Trigger change event.
        name_input.evaluateJavaScript("""
            var event = document.createEvent("HTMLEvents");
            event.initEvent("change", false, true);
            this.dispatchEvent(event);
        """)

        # Let WebKit run.
        yield deferLater(reactor, 0, lambda: None)

        h1 = frame.findFirstElement('#the-basics + div .well h1')
        text = h1.toPlainText()
        returnValue([AngularJSHelloText(text=text)])
