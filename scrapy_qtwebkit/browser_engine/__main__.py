import argparse
import importlib
import logging

from twisted.internet.endpoints import StandardIOEndpoint, serverFromString
from twisted.python.log import PythonLoggingObserver
from twisted.spread import jelly, pb

from . import BrowserManager


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
log_observer = PythonLoggingObserver()
log_observer.start()

parser = argparse.ArgumentParser()
parser.add_argument('--browser-engine', default='.qt')
parser.add_argument('address')
args = parser.parse_args()


browser_engine = importlib.import_module(args.browser_engine,
                                         package=__package__)

setup_pre_reactor = getattr(browser_engine, '_setup_pre_reactor', None)
if setup_pre_reactor:
    setup_pre_reactor()

from twisted.internet import reactor


if args.address == 'stdio':
    server_endpoint = StandardIOEndpoint(reactor)
else:
    server_endpoint = serverFromString(reactor, args.address)

server_factory = pb.PBServerFactory(
    BrowserManager(browser_engine.Browser),
    unsafeTracebacks=True,
    security=jelly.DummySecurityOptions()
)
server_endpoint.listen(server_factory)
reactor.run()
