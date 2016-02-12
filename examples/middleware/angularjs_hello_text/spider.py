from scrapy import Field, Item, Spider

from scrapy_qtwebkit import QtWebKitRequest


class AngularJSHelloText(Item):
    text = Field()


class AngularJSHelloTextSpider(Spider):
    name = 'angularjs_hello_text'

    def start_requests(self):
        yield QtWebKitRequest("https://angularjs.org/")

    def parse(self, response):
        text = ''.join(response.css('#the-basics + div .well h1::text'
                                    ).extract())
        yield AngularJSHelloText(text=text)
