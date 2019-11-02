from twisted.spread import pb

from .cookies import RemoteCookieJar, RemotelyAccessibleCookieJar


pb.setUnjellyableForClass(RemotelyAccessibleCookieJar, RemoteCookieJar)
