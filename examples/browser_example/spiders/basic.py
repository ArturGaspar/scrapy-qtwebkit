from scrapy import Spider
from twisted.internet.defer import inlineCallbacks

from scrapy_qtwebkit.middleware import BrowserRequest


class ExampleSpider(Spider):
    """Requests example.com and changes the page title with Javascript."""

    name = 'basic'
    allowed_domains = ['example.com']

    def start_requests(self):
        yield BrowserRequest("https://example.com/",
                             meta={'browser_response': True},
                             dont_filter=True)

    @inlineCallbacks
    def parse(self, response):
        items = []
        items.append(
            {"title": response.xpath('/html/head/title/text()').extract_first()}
        )

        yield response.webpage.run_script("""
            document.title = "Javascript!";
        """)

        yield response.update_body()

        items.append(
            {"title": response.xpath('/html/head/title/text()').extract_first()}
        )

        return items
