import datetime
import importlib
import json
import logging.config
import os
import pathlib
import sqlite3
import sys
import zlib
from functools import wraps
from string import Formatter
from types import ModuleType

import box
import dill
import slider
import sqlitedict
from twisted.internet import reactor

import osu

logger = logging.getLogger(__name__)
URL_REGEX = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""


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

    def trace_reload(recursed_module, depth):  # recursive
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
    def isfloat(value):
        try:
            float(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def clamp(n, min_n, max_n):
        return max(min(max_n, n), min_n)

    @staticmethod
    def strfdelta(tdelta, fmt):
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
    def check_user_in_db(source, bot, msg_type):
        user_in = False

        if msg_type == "ftm":
            if source.nick not in bot.user_pref:
                bot.user_pref[source.nick] = UserPref(source.user, None)
            else:
                user_in = True
        elif msg_type == "um":
            if source.nick not in bot.user_pref or bool(bot.user_pref[source.nick].updated) is False:
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
    def check_mode_in_db(source, bot, beatmap_data, np=False):
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
    def set_pref(source, bot, mode):
        if source not in bot.user_pref:
            bot.user_pref[source.nick] = UserPref(source.user, mode)
        else:
            x = bot.user_pref[source.nick]
            x.mode = mode
            bot.user_pref[source.nick] = x

        bot.user_pref.commit()

    @staticmethod
    def create_sqlite_dict(db, table):
        def encode(obj):
            return sqlite3.Binary(zlib.compress(dill.dumps(obj, dill.HIGHEST_PROTOCOL)))

        def decode(obj):
            return dill.loads(zlib.decompress(bytes(obj)))

        return sqlitedict.SqliteDict(db, tablename=table, encode=encode, decode=decode, autocommit=True)

    @staticmethod
    def update_db():
        user_pref = Utils.create_sqlite_dict("./userpref2.db", "userpref")
        old_user_pref = sqlite3.connect("./userpref.db")
        db_cursor = old_user_pref.cursor()
        try:
            bool(db_cursor.execute("SELECT mode FROM userdb").fetchone()[0])
            logger.info("updating db...")
            db_cursor.execute("SELECT COUNT(*) FROM userdb")
            count = db_cursor.fetchone()[0]
            db_cursor.execute("SELECT * FROM userdb")
            for i in range(count):
                row = db_cursor.fetchone()
                user_pref[row[0]] = UserPref(None, row[1])
            old_user_pref.close()
            user_pref.close()
            os.remove("userpref.db")
            os.rename("userpref2.db", "userpref.db")
            logger.info("update completed!")
        except:
            logger.info("userdb already updated")


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
        reactor.callLater(2, reactor.callFromThread, reactor.stop)

    kill = die
    stop = die
    end = die

    @is_owner()
    @command()
    def test(self, bot, e):
        bot.msg(e.source.nick, str(bot.recommend[e.source.nick]))

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


class UserPref:
    def __init__(self, user_id, mode, updated=False):
        self.user_id = user_id
        self.mode = mode
        self.updated = updated
