from scrapy import Spider

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater

from scrapy_qtwebkit import QtWebKitRequest


class SumSpider(Spider):
    name = 'sum'

    def start_requests(self):
        yield QtWebKitRequest("http://localhost:8000/interaction.html",
                              meta={'qwebpage_response': True})

    @inlineCallbacks
    def parse(self, response):
        webpage = response.webpage
        frame = webpage.mainFrame()

        input1 = frame.findFirstElement('#input1')
        input2 = frame.findFirstElement('#input2')
        input1.setAttribute('value', "10")
        input2.setAttribute('value', "5")

        button = frame.findFirstElement('#button')
        button.evaluateJavaScript("""
            var event = new Event("click");
            this.dispatchEvent(event);
        """)

        # Let WebKit run.
        yield deferLater(reactor, 0, lambda: None)

        result = frame.findFirstElement('#result')
        text = result.toPlainText()
        returnValue([{"result": text}])
