from twisted.spread import pb

from .cookies import RemoteCookieJar, RemotelyAccessbileCookieJar


pb.setUnjellyableForClass(RemotelyAccessbileCookieJar, RemoteCookieJar)
