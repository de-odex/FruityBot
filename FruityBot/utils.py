import datetime
import importlib
import json
import logging
import logging.config
import pathlib
import sqlite3
import sys
import zlib
from collections import MutableMapping, OrderedDict
from string import Formatter
from types import ModuleType

import box
import dill
import sqlitedict
from irc.client import NickMask

from .exceptions import MissingPreferenceError
from slider import Beatmap, GameMode

logger = logging.getLogger(__name__)


def reload_all(top_module, max_depth=20):
    """
    A reload function, which recursively traverses through
    all submodules of top_module and reloads them from most-
    nested to least-nested. Only modules containing __file__
    attribute could be reloaded.

    Returns a dict of not reloaded(due to errors) modules:
      key = module, value = exception
    Optional attribute max_depth defines maximum recursion
    limit to avoid infinite loops while tracing
    """
    for_reload = {}  # modules to reload: K=module, V=depth

    importlib.invalidate_caches()

    def trace_reload(recursed_module: ModuleType, depth: int):  # recursive
        depth += 1
        if type(recursed_module) == ModuleType and depth < max_depth:
            # if recursed_module is deeper and could be reloaded
            if (for_reload.get(recursed_module, 0) < depth
                and hasattr(recursed_module, '__file__')):
                for_reload[recursed_module] = depth
            # trace through all attributes recursively
            for attr in recursed_module.__dict__.values():
                trace_reload(attr, depth)

    trace_reload(top_module, 0)  # start tracing
    reload_list = sorted(for_reload, reverse=True,
                         key=lambda k: for_reload[k])
    not_reloaded = {}
    if logging in reload_list:
        reload_list.remove(logging)
    for module in reload_list:
        try:
            importlib.reload(module)
        except:  # catch and write all errors
            not_reloaded[module] = sys.exc_info()[0]
    return not_reloaded


def is_type(val_type, value) -> bool:
    try:
        val_type(value)
        return True
    except ValueError:
        return False


def strfdelta(tdelta: datetime.timedelta, fmt: str) -> str:
    f = Formatter()
    d = {}
    l = {'D': 86400, 'H': 3600, 'M': 60, 'S': 1}
    k = list(map(lambda x: x[1], list(f.parse(fmt))))
    rem = int(tdelta.total_seconds())

    for i in ('D', 'H', 'M', 'S'):
        if i in k and i in l.keys():
            d[i], rem = divmod(rem, l[i])

    return f.format(fmt, **d)


def convert_time(time):
    if type(time) == str:
        return datetime.datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
    elif type(time) == datetime.datetime:
        return time
    else:
        raise TypeError


def check_mode_in_db(source: NickMask, bot, beatmap_mode: int, np: bool = False):
    if beatmap_mode != 0:
        if np:
            mode_db = bot.user_pref.get(source.nick).mode
            if mode_db is None:
                bot.msg(
                    source.nick, f"Automatically setting mode to {GameMode(beatmap_mode).name}... "
                    f"use \"!set mode [catch|mania|taiko]\" to change"
                )
                set_pref(source, bot, 'mode', beatmap_mode)
        return beatmap_mode
    else:
        mode_db = bot.user_pref.get(source.nick).mode
        if mode_db is None:
            bot.msg(source.nick, "Please set a mode with !set mode [catch|mania|taiko]")
            raise MissingPreferenceError
        else:
            return mode_db


def set_pref(source: NickMask, bot, pref: str, arg):
    bot.user_pref[source.nick] = {pref: arg}


def load_db(db: str or pathlib.Path, table: str):
    def encode(obj):
        return sqlite3.Binary(zlib.compress(dill.dumps(obj, dill.HIGHEST_PROTOCOL)))

    def decode(obj):
        return dill.loads(zlib.decompress(bytes(obj)))

    return sqlitedict.SqliteDict(str(pathlib.Path(db)), tablename=table, encode=encode, decode=decode, autocommit=True)


class Config:
    def __init__(self, conf_filename: pathlib.Path):
        self.filename = conf_filename
        self._config = box.Box(json.load(open(pathlib.Path(conf_filename).absolute(), "r")))

    def __call__(self, *args, **kwargs):
        return self._config

    @property
    def config(self):
        return self._config


# class UserPref:
#     DEPRECATED
#     def __init__(self, *pref, file=None):
#         user_database = file
#         self.tables: dict = {}
#         for i in pref:
#             self.tables[i] = load_db(user_database, i)
#
#     def __setitem__(self, key, item: dict):
#         for k, v in item.items():
#             # key is user, k is type
#             # tables is keyed type then user (tables[type][user])
#             # therefore it's self.tables[k][key]
#             # 多分...
#             self.tables[k][key] = v
#
#     def __getitem__(self, key):
#         if not self.has_key(key):
#             raise KeyError(f"Key '{key}' not in database")
#         return box.Box({
#             k: v.get(key) for k, v in self.tables.items()
#         })
#         # yet again key is user, k is type
#
#     def __contains__(self, item):
#         return any(item in db for __, db in self.tables.items())
#
#     def __repr__(self):
#         return f"<{type(self).__qualname__}: {repr({k: repr(v) for k, v in self.tables.items()})}>"
#
#     def __len__(self):
#         raise NotImplementedError(f"Use len(self.db[table])")
#
#     def has_key(self, k):
#         return self.__contains__(k)
#
#     def pop(self, *args):
#         return self.__dict__.pop(*args)
#
#     def keys(self):
#         return tuple(sorted(i for i in self.tables))
#
#     def values(self):
#         return tuple(sorted(i for __, i in self.tables))
#
#     def items(self):
#         return tuple(sorted((k, v) for k, v in self.tables.items()))


class RecentDict(MutableMapping):
    def __init__(self, maxlen: int, items: OrderedDict = None):
        self._maxlen = maxlen
        self.d = OrderedDict()
        if items:
            for k, v in items:
                self[k] = v

    @property
    def maxlen(self):
        return self._maxlen

    def __check_size_limit(self):
        while len(self.d) >= self.maxlen:
            self.d.popitem(last=False)

    def __getitem__(self, key):
        self.d.move_to_end(key)
        return self.d[key]

    def __setitem__(self, key, value):
        if key in self.d:
            self.d.move_to_end(key)
        else:
            self.__check_size_limit()
            self.d[key] = value

    def __delitem__(self, key):
        del self.d[key]

    def __iter__(self):
        return self.d.__iter__()

    def __len__(self):
        return len(self.d)

    def __repr__(self):
        return (
            f'<{type(self).__qualname__}: '
            f'{[(k, v) for k, v in self.d.items()]}>'
        )


class ThreadDict(RecentDict):
    def __check_size_limit(self):
        if len(self.d) == self.maxlen:
            self.d.popitem(last=False)[1].stop()
