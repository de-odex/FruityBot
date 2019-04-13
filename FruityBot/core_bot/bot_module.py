import logging
import zlib
from abc import ABC
from functools import partial, update_wrapper, wraps
from typing import Iterable

import dill

from FruityBot.localize import tl

logger = logging.getLogger(__name__)


def command(func=None, *, cmd_help=None, aliases=tuple(), include_funcname=True):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)

        wrapper.__dict__["command"] = True
        fname = f.__name__ if not f.__name__.startswith("cmd_") else f.__name__[4:]
        wrapper.__dict__["cmd_help"] = cmd_help if cmd_help and type(cmd_help) is str else f"help.{fname}"

        if not aliases:
            wrapper.__dict__["cmd_aliases"] = (fname,)
        elif isinstance(aliases, Iterable):
            if include_funcname:
                wrapper.__dict__["cmd_aliases"] = (fname, *aliases)
            else:
                wrapper.__dict__["cmd_aliases"] = tuple(aliases)
        logger.debug(f"command decorator | command {wrapper.__name__} with aliases {wrapper.__dict__['cmd_aliases']}")
        return wrapper

    # if func is a function
    if callable(func) and hasattr(func, '__name__'):
        return decorator(func)
    elif func is None:  # else if decorator has parentheses
        return decorator


def is_owner(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        self, e = args
        if e.source.nick == self.bot.Config().main.owner:
            return f(*args, **kwargs)
        else:
            self.bot.msg(e.source.nick, tl("general.no_permission", self.bot.user_pref[e.source.nick].locale))

    return wrapper


def requires_args(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        self, e = args
        if len(e.arguments) >= 2:
            return f(*args, **kwargs)
        else:
            self.bot.msg(e.source.nick, tl("general.no_arguments", self.bot.user_pref[e.source.nick].locale))

    return wrapper


class cached:
    def __init__(self, f):
        self._f = f
        update_wrapper(self, f)

    def __call__(self, *args, **kwargs):
        f_self, *__ = args
        f = self._f
        cache_redis = f_self.bot.cache_redis

        # check if saved in redis
        redis_key = f"{type(f_self).__module__}.{type(f_self).__name__}.{f.__name__}_{'_'.join(str(args))}"

        if cache_redis.exists(redis_key):
            return dill.loads(zlib.decompress(bytes(cache_redis.get(redis_key))))
        else:
            result = f(*args, **kwargs)
            cache_redis.set(redis_key,
                            zlib.compress(dill.dumps(result, dill.HIGHEST_PROTOCOL)),
                            ex=60 * 60 * 12)  # 12 hours
            return result

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return partial(self.__call__, instance)


class Module(ABC):
    def __init__(self, state, bot):
        self.commands = []
        self.state = state
        self.bot = bot
        super().__init__()

    def get_functions(self):
        function_names = [func for func in dir(self)
                          if callable(getattr(self, func))
                          and not func.startswith("_")
                          and getattr(self, func).__dict__.get('command', False)]

        functions = [getattr(self, func) for func in function_names]

        logger.debug(f"Module.get_functions | functions in {self.__class__.__name__}: {function_names}")
        return function_names, functions
