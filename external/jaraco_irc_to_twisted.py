import six


class NickMask(six.text_type):
    """
    A nickmask (the source of an Event)
    >>> nm = NickMask('pinky!username@example.com')
    >>> nm.nick
    'pinky'
    >>> nm.host
    'example.com'
    >>> nm.user
    'username'
    >>> isinstance(nm, six.text_type)
    True
    >>> nm = 'красный!red@yahoo.ru'
    >>> if not six.PY3: nm = nm.decode('utf-8')
    >>> nm = NickMask(nm)
    >>> isinstance(nm.nick, six.text_type)
    True
    Some messages omit the userhost. In that case, None is returned.
    >>> nm = NickMask('irc.server.net')
    >>> nm.nick
    'irc.server.net'
    >>> nm.userhost
    >>> nm.host
    >>> nm.user
    """
    @classmethod
    def from_params(cls, nick, user, host):
        return cls('{nick}!{user}@{host}'.format(**vars()))

    @property
    def nick(self):
        nick, sep, userhost = self.partition("!")
        return nick

    @property
    def userhost(self):
        nick, sep, userhost = self.partition("!")
        return userhost or None

    @property
    def host(self):
        nick, sep, userhost = self.partition("!")
        user, sep, host = userhost.partition('@')
        return host or None

    @property
    def user(self):
        nick, sep, userhost = self.partition("!")
        user, sep, host = userhost.partition('@')
        return user or None

    @classmethod
    def from_group(cls, group):
        return cls(group) if group else None