import datetime
import importlib
import json
import logging.config
import os
import pathlib
import sqlite3
import sys
import zlib
from collections import OrderedDict
from functools import wraps
from string import Formatter
from types import ModuleType

import box
import dill
import sqlitedict
from irc.client import NickMask
from twisted.internet import reactor

import osu
import slider
from bot import FruityBot
from slider import Beatmap

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
    for_reload = dict()  # modules to reload: K=module, V=depth

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
    not_reloaded = dict()
    if logging in reload_list:
        reload_list.remove(logging)
    for module in reload_list:
        try:
            importlib.reload(module)
        except:  # catch and write all errors
            not_reloaded[module] = sys.exc_info()[0]
    return not_reloaded


def is_owner():
    def is_owner_deco(f):

        @wraps(f)
        def wrapper(*args, **kwargs):
            self, bot, e = args
            if e.source.nick == bot.Config.config.main.owner:
                f(*args, **kwargs)
            else:
                bot.msg(e.source.nick, "You do not have the permissions to run this command!")

        return wrapper

    return is_owner_deco


def command(remove_cmd=False):
    def command_deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            self, bot, e = args
            try:
                if remove_cmd:
                    e.arguments[0] = e.arguments[0][len(f.__name__) + 1:]
                    args = self, bot, e
                    f(*args, **kwargs)
                else:
                    f(*args, **kwargs)
            except IndexError:
                bot.msg(e.source.nick, "No arguments were passed.")
                logger.exception("Argument Exception")
            except Exception as exc:
                bot.msg(e.source.nick, "A general error has occurred. Error: " + type(exc).__name__)
                logger.exception("General Exception")

        return wrapper

    return command_deco


class Utils:
    @staticmethod
    def isfloat(value: float):
        try:
            float(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def clamp(n, min_n, max_n):
        return max(min(max_n, n), min_n)

    @staticmethod
    def strfdelta(tdelta: datetime.timedelta, fmt: str):
        f = Formatter()
        d = {}
        l = {'D': 86400, 'H': 3600, 'M': 60, 'S': 1}
        k = list(map(lambda x: x[1], list(f.parse(fmt))))
        rem = int(tdelta.total_seconds())

        for i in ('D', 'H', 'M', 'S'):
            if i in k and i in l.keys():
                d[i], rem = divmod(rem, l[i])

        return f.format(fmt, **d)

    @staticmethod
    def check_user_in_db(source: NickMask, bot: FruityBot, msg_type: str):
        user_in = False

        if msg_type == "ftm":
            if source.nick not in bot.user_pref:
                bot.user_pref[source.nick] = UserPref(source.user, None)
            else:
                user_in = True
        elif msg_type == "um":
            if source.nick not in bot.user_pref or not bool(bot.user_pref[source.nick].updated):
                if source.nick not in bot.user_pref:
                    bot.user_pref[source.nick] = UserPref(source.user, None, updated=True)
                else:
                    x = bot.user_pref[source.nick]
                    x.updated = True
                    bot.user_pref[source.nick] = x
            else:
                user_in = True

        bot.user_pref.commit()
        return user_in

    @staticmethod
    def check_mode_in_db(source: NickMask, bot: FruityBot, beatmap_data: Beatmap, np: bool = False):
        if int(beatmap_data.mode) != 0:
            mode = int(beatmap_data.mode)
            if np:
                mode_db = bot.user_pref[source.nick].mode if source.nick in bot.user_pref else None
                if mode_db is None:
                    bot.msg(source.nick, "Automatically setting mode to " + slider.GameMode(mode).name + "... " +
                            "use \"!set mode [catch|mania|taiko]\" to change")
                    Utils.set_pref(source, bot, mode)
            return mode
        else:
            mode_db = bot.user_pref[source.nick].mode if source.nick in bot.user_pref else None
            if mode_db is None:
                bot.msg(source.nick, "Please set a mode with !set mode [catch|mania|taiko]")
                return -1
            else:
                return mode_db

    @staticmethod
    def set_pref(source: NickMask, bot: FruityBot, mode: int):
        if source.nick not in bot.user_pref:
            bot.user_pref[source.nick] = UserPref(source.user, mode)
        else:
            x = bot.user_pref[source.nick]
            x.mode = mode
            bot.user_pref[source.nick] = x

    @staticmethod
    def create_sqlite_dict(db: str, table: str):
        def encode(obj):
            return sqlite3.Binary(zlib.compress(dill.dumps(obj, dill.HIGHEST_PROTOCOL)))

        def decode(obj):
            return dill.loads(zlib.decompress(bytes(obj)))

        return sqlitedict.SqliteDict(db, tablename=table, encode=encode, decode=decode, autocommit=True)


class Commands:
    def __init__(self, bot, config):
        self.Config = config
        self.lib_dir = pathlib.Path("./osulib").absolute()
        if not self.lib_dir.exists():
            os.makedirs(self.lib_dir)
            self.osu_library = slider.library.Library.create_db(self.lib_dir)
            logger.info("Created osu! library")
        else:
            self.osu_library = slider.library.Library(self.lib_dir)
        self.osu_api_client = slider.client.Client(self.osu_library, self.Config.config.osu.api, max_requests=60)
        self.osu_non_std_library = osu.Osu(self, bot)

    @is_owner()
    @command()
    def disconnect(self, bot, e):
        bot.msg(e.source.nick, "Reconnecting bot...")
        bot.quit()

    @is_owner()
    @command()
    def die(self, bot, e):
        bot.msg(e.source.nick, "Shutting down...")
        bot.user_pref.close()
        bot.recommend.close()
        reactor.callLater(2, reactor.callFromThread, reactor.stop)

    kill = die
    stop = die
    end = die

    @is_owner()
    @command()
    def test(self, bot, e):
        bot.msg(e.source.nick, "www")

    @is_owner()
    @command()
    def resetupdate(self, bot, e):
        bot.msg(e.source.nick, "Resetting all users...")
        for i in bot.user_pref:
            x = bot.user_pref[i]
            x.updated = False
            bot.user_pref[i] = x
        bot.user_pref.commit()
        bot.msg(e.source.nick, "All userpref.updated reset!")

    @is_owner()
    @command()
    def resetosu(self, bot, e):
        bot.msg(e.source.nick, "Clearing self.users...")
        bot.users = {}
        bot.msg(e.source.nick, "self.users cleared!")

    @command()
    def help(self, bot, e):
        bot.msg(e.source.nick, "Need help? Check [https://github.com/de-odex/FruityBot/wiki the wiki] "
                               "for commands.")

    h = help

    @command()
    def uptime(self, bot, e):
        elapsed = (datetime.datetime.now() - bot.start_time)
        if elapsed.days:
            elapsed_str = Utils.strfdelta(elapsed, "{D} days {H}h;{M:02}m;{S:02}s")
        elif elapsed.total_seconds() // 3600:
            elapsed_str = Utils.strfdelta(elapsed, "{H}h;{M:02}m;{S:02}s")
        elif divmod(elapsed.total_seconds(), 3600)[1] // 60:
            elapsed_str = Utils.strfdelta(elapsed, "{M} minutes and {S:02} seconds")
        else:
            elapsed_str = Utils.strfdelta(elapsed, "{S} seconds")
        bot.msg(e.source.nick, elapsed_str + " since start.")

    @command()
    def time(self, bot, e):
        bot.msg(e.source.nick, "Local time: " + datetime.datetime.now().strftime("%B %d %H;%M;%S"))

    @command(remove_cmd=True)
    def set(self, bot, e):
        split_msg2 = e.arguments[0].split()

        if split_msg2[0] == "mode":
            if split_msg2[1].lower() in ["catch", "ctb", "c", "2"]:
                mode = 2
            elif split_msg2[1].lower() in ["mania", "m", "3"]:
                mode = 3
            elif split_msg2[1].lower() in ["taiko", "t", "1"]:
                mode = 1
            elif split_msg2[1].lower() in ["standard", "std", "osu", "o", "0"]:
                bot.msg(e.source.nick, "Please message Tillerino for standard pp predictions!")
                return
            else:
                bot.msg(e.source.nick, "Invalid setting")
                return
            Utils.set_pref(e.source, bot, mode)
            bot.msg(e.source.nick, "Setting \"" + split_msg2[0] + "\" was successfully "
                                                                  "set to \"" + split_msg2[1] + "\"!")
        else:
            return bot.msg(e.source.nick, "Invalid setting")

    # Osu! ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @command()
    def recommend(self, bot, e):
        user = bot.users.setdefault(e.source.nick, osu.OsuUser(e.source.nick, bot.user_pref))
        try:
            if (bot.recommend[user.user_id] is not None or bot.recommend[user.user_id] is not [-1, None, None, None]) \
                    and e.arguments[0].split()[1] == "reset":
                if e.arguments[0].split()[1] == "reset":
                    bot.recommend[user.user_id] = None
                    bot.msg(e.source.nick, "Reset your recommendations!")
                elif e.arguments[0].split()[1] == "reload":
                    x = bot.recommend[user.user_id]
                    x[bot.users[e.source.nick].preferences[e.source.nick].mode] = \
                        osu.Recommendation(rec_list=x.rec_list, i=0, last_refresh=x.last_refresh)
                    bot.recommend[user.user_id] = x
                    bot.msg(e.source.nick, "Reloaded your recommendations!")
        except:
            pass
        self.osu_non_std_library.recommend(user, bot, e)

    cmd_r = recommend

    @command()
    def np(self, bot, e):
        user = bot.users.setdefault(e.source.nick, osu.OsuUser(e.source.nick, bot.user_pref))
        self.osu_non_std_library.np(user, bot, e)

    @command()
    def cmd_with(self, bot, e):
        if e.source.nick in bot.users:
            user = bot.users[e.source.nick]
            self.osu_non_std_library.acm_mod(user, bot, e)
        else:
            return bot.msg(e.source.nick, "You haven't /np'd me anything yet!")

    acc = cmd_with


class Config:
    def __init__(self, conf_filename):
        self.config = box.Box(json.load(open(pathlib.Path("./" + conf_filename), "r")))

    def __call__(self, *args, **kwargs):
        return self.config


class UserPref:
    def __init__(self, user_id, mode, updated=False):
        self.user_id = user_id
        self.mode = mode
        self.updated = updated


class ColorFormatter(logging.Formatter):
    from colorama import Fore, Back, Style
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

    COLORS = {
        'WARNING' : (Style.DIM + Fore.BLACK, Back.YELLOW),
        'INFO'    : (Style.BRIGHT + Fore.WHITE, Back.CYAN),
        'DEBUG'   : (Style.NORMAL + Fore.WHITE, Back.BLUE),
        'CRITICAL': (Style.DIM + Fore.BLACK, Back.YELLOW),
        'ERROR'   : (Style.BRIGHT + Fore.WHITE, Back.RED),
    }

    CCOLORS = {
        "BLACK": BLACK,
        "RED": RED,
        "GREEN": GREEN,
        "YELLOW": YELLOW,
        "BLUE": BLUE,
        "MAGENTA": MAGENTA,
        "CYAN": CYAN,
        "WHITE": WHITE,
    }

    COLOR_SEQ = "\033[1;%dm"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS[levelname][0]
        bg_color = self.COLORS[levelname][1]
        message = logging.Formatter.format(self, record)
        message = message.replace("$RESET", self.Style.RESET_ALL) \
            .replace("$BRIGHT", self.Style.BRIGHT) \
            .replace("$COLOR", color) \
            .replace("$BGCOLOR", bg_color)
        for k, v in self.CCOLORS.items():
            message = message.replace("$" + k, self.COLOR_SEQ % (v + 30)) \
                .replace("$BG" + k, self.COLOR_SEQ % (v + 40))
        return message + self.Style.RESET_ALL


class RecentDict(OrderedDict):
    def __init__(self, size_limit: int, *args, **kwargs):
        self.size_limit = size_limit
        super().__init__(*args, **kwargs)
        self.__check_size_limit()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.__check_size_limit()

    def __getitem__(self, key):
        value = super().__getitem__(key)
        del self[key]
        self[key] = value
        return value

    def __check_size_limit(self):
        if self.size_limit is not None:
            while len(self) > self.size_limit:
                self.popitem(last=False)
