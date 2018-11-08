from scrapy import Spider

from scrapy_qtwebkit import QtWebKitRequest


class HelloWorldSpider(Spider):
    name = 'hello_world'

    def start_requests(self):
        yield QtWebKitRequest("http://localhost:8000/resources.html")

    def parse(self, response):
        message = response.xpath('id("message")/text()').extract_first()
        yield {"message": message}
