import json
import logging.config
import math
import operator
import os
import pathlib
import re
import sqlite3
import datetime
import urllib.parse
import zlib
from functools import wraps
from itertools import islice
from string import Formatter
from collections import defaultdict, Counter, OrderedDict

import box
import dill
import slider
import sqlitedict
from twisted.internet import reactor, threads, defer

logger = logging.getLogger(__name__)
URL_REGEX = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""


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
    def create_db(db, table):
        def encode(obj):
            return sqlite3.Binary(zlib.compress(dill.dumps(obj, dill.HIGHEST_PROTOCOL)))

        def decode(obj):
            return dill.loads(zlib.decompress(bytes(obj)))

        return sqlitedict.SqliteDict(db, tablename=table, encode=encode, decode=decode, autocommit=True)

    @staticmethod
    def update_db():
        user_pref = Utils.create_db("./userpref2.db", "userpref")
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
        self.osu_api_client = slider.client.Client(self.osu_library, self.Config.config.osu.api)
        self.osu_non_std_library = Osu(self, bot)

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
        bot.msg(e.source.nick, str(((bot.users[e.source.nick].recommendations))))

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
        bot.msg(e.source.nick, "Still under construction...")
        bot.msg(e.source.nick, "Showing debug values")
        user = bot.users.setdefault(e.source.nick, OsuUser(e.source.nick, bot.user_pref))
        self.osu_non_std_library.recommend(user, bot, e)

    cmd_r = recommend

    @command()
    def np(self, bot, e):
        user = bot.users.setdefault(e.source.nick, OsuUser(e.source.nick, bot.user_pref))
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


class OsuUser:
    def __init__(self, user_id, preferences):
        self.preferences = preferences
        self.user_id = user_id
        self.user_client = False
        self.last_beatmap = False
        self.last_mod = False
        self.last_kwargs = False
        self.top_plays = [-1, False, False, False]  # per mode, will be arrays
        self.recommendations = False


class Osu:
    def __init__(self, cmd, bot):
        self.cmd = cmd  # use self.cmd.osu_library to get the library, to survive reloads
        self.bot = bot

    @staticmethod
    def key_count(beatmap):
        percent = sum(1 for x in beatmap.hit_objects if
                      isinstance(x, slider.beatmap.Slider) or
                      isinstance(x, slider.beatmap.Spinner)) \
                  / len(beatmap.hit_objects)
        if percent < 0.2:
            return 7
        if percent < 0.3 or round(beatmap.circle_size) >= 5:
            return 7 if round(beatmap.overall_difficulty) > 5 else 6
        if percent > 0.6:
            return 5 if round(beatmap.overall_difficulty) > 4 else 4
        return max(4, min(round(beatmap.overall_difficulty) + 1, 7))

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def np(self, osu_user, bot, e):
        osu_user.last_mod = False
        osu_user.last_kwargs = False

        link_str = re.findall(
            URL_REGEX,
            e.arguments[0])
        link = urllib.parse.urlparse(link_str[0])
        if link.path.split("/")[1] == "b":
            beatmap_id = link.path.split("/")[2].split("&")[0]
        elif link.path.split("/")[1] == "beatmapsets" and link.fragment.split("/")[1].isdigit():
            beatmap_id = link.fragment.split("/")[1]
        else:
            return bot.msg(e.source.nick, "This is a beatmap set, not a beatmap")
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        beatmap_data = self.cmd.osu_library.lookup_by_id(beatmap_id, download=True, save=True)
        beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=beatmap_id, include_converted_beatmaps=True)
        if not beatmap_data_api:
            raise Exception  # ModeError

        mode = Utils.check_mode_in_db(e.source, self.bot, beatmap_data, np=True)

        if mode == -1:
            return

        beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                               include_converted_beatmaps=True,
                                                               game_mode=slider.GameMode(mode))

        if beatmap_data_api.max_combo is None and mode is not 3:
            beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                                   include_converted_beatmaps=True)

        osu_user.last_beatmap = (beatmap_data, beatmap_data_api, mode, beatmap_id)
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
        bm_time = Utils.strfdelta(datetime.timedelta(seconds=int(beatmap_data_api.hit_length.seconds),
                                                     milliseconds=beatmap_data_api.hit_length.seconds -
                                                     int(beatmap_data_api.hit_length.seconds)), "{M:02}:{S:02}")

        if mode == 2:
            pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=i)) for i in
                              [100, 99.5, 99, 98.5])
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " AR" + str(beatmap_data.approach_rate) \
                        + " MAX" + str(beatmap_data_api.max_combo)
            bot.msg(e.source.nick, artist_name
                    + " | osu!catch"
                    + " | SS: " + pp_values[0] + "pp"
                    + " | 99.5% FC: " + pp_values[1] + "pp"
                    + " | 99% FC: " + pp_values[2] + "pp"
                    + " | 98.5% FC: " + pp_values[3] + "pp"
                    + " | " + end_props)
        elif mode == 3:
            pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=i[0], score=i[1]))
                              for i in [(100, 1000000), (99, 970000), (97, 900000)])
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " OD" + str(beatmap_data.overall_difficulty) \
                        + " " + str(Osu.key_count(beatmap_data)) + "key" \
                        + " OBJ" + str(len(beatmap_data.hit_objects))
            bot.msg(e.source.nick, artist_name
                    + " | osu!mania"
                    + " | SS: " + pp_values[0] + "pp"
                    + " | 99% 970k: " + pp_values[1] + "pp"
                    + " | 97% 900k: " + pp_values[2] + "pp"
                    + " | " + end_props)
        elif mode == 1:
            pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=i))
                              for i in [100, 99, 98])
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " OD" + str(beatmap_data.overall_difficulty) \
                        + " MAX" + str(beatmap_data.max_combo)
            bot.msg(e.source.nick, artist_name
                    + " | osu!taiko"
                    + " | SS: " + pp_values[0] + "pp"
                    + " | 99% FC: " + pp_values[1] + "pp"
                    + " | 98% FC: " + pp_values[2] + "pp"
                    + " | " + end_props)
        return True

    def acm_mod(self, osu_user, bot, e):
        split_msg = e.arguments[0].split()

        mods_name = ""

        beatmap_data, beatmap_data_api, mode_api, beatmap_id = osu_user.last_beatmap

        mode = Utils.check_mode_in_db(e.source, self.bot, beatmap_data)

        if mode_api != mode:
            beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=beatmap_id,
                                                               include_converted_beatmaps=True,
                                                               game_mode=slider.game_mode.GameMode(mode))

        max_combo = int(beatmap_data_api.max_combo) if beatmap_data_api.max_combo else int(beatmap_data.max_combo)
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
        bm_time = Utils.strfdelta(datetime.timedelta(seconds=int(beatmap_data_api.hit_length.seconds),
                                                     milliseconds=beatmap_data_api.hit_length.seconds -
                                                                  int(beatmap_data_api.hit_length.seconds)),
                                  "{M:02}:{S:02}")
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if split_msg[0] == "acc":

            # checks for former mod data if any
            if not osu_user.last_mod:
                mods = 0
            else:
                mods = osu_user.last_mod

            # reads args of message
            acc = combo = miss = score = 0
            for i in split_msg:
                if Utils.isfloat(i) or i.endswith(("%",)):
                    acc = float(i.replace("%", ""))
                elif i.endswith(("x",)):
                    combo = i.rstrip("x")
                elif i.endswith(("m",)):
                    miss = i.rstrip("m")
                elif i.endswith(("s",)):
                    score = i.rstrip("s")
                else:
                    pass

            if mods & 1 == 1:
                mods_name += "NF"
            if mods & 2 == 2:
                mods_name += "EZ"
            if mods & 8 == 8:
                mods_name += "HD"
            if mods & 1024 == 1024:
                mods_name += "FL"
            if mods == 0:
                mods_name = "NoMod"

            if mode == 2:
                if not combo:
                    combo = int(beatmap_data_api.max_combo)
                if not miss:
                    miss = 0

                try:
                    miss = int(miss)
                    miss = Utils.clamp(miss, 0, max_combo - 1)
                except:
                    return bot.msg(e.source.nick, "You MISSed something there")
                try:
                    combo = int(combo)
                    combo = Utils.clamp(combo, 0, max_combo)
                except:
                    return bot.msg(e.source.nick, "You made a mistake with your combo!")
                try:
                    acc = float(acc)
                    acc = Utils.clamp(acc, 0.0, 100.0)
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, combo, miss]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode, acc=acc,
                                                  player_combo=combo, miss=miss,
                                                  mods=mods)),)
                acc_combo_miss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " AR" + str(beatmap_data.approach_rate) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                bot.msg(e.source.nick, artist_name
                        + " | osu!catch"
                        + " | " + acc_combo_miss + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
            elif mode == 3:
                try:
                    score = int(score)
                    if 1000000 >= score >= 0:
                        score = score
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "You messed up your score there...")
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, score]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode=mode, acc=acc,
                                                  score=score, mods=mods)),)
                acc_score = str(acc) + "% " + str(score) + " " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " " + str(Osu.key_count(beatmap_data)) + "key" \
                            + " OBJ" + str(len(beatmap_data.hit_objects))
                bot.msg(e.source.nick, artist_name
                        + " | osu!mania"
                        + " | " + acc_score + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
            elif mode == 1:
                try:
                    miss = int(miss)
                    if miss < max_combo or miss >= 0:
                        miss = miss
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "You MISSed something there")
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, miss]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode=mode, acc=acc,
                                                  miss=miss, mods=mods)),)
                acc_miss = str(acc) + "% " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                bot.msg(e.source.nick, artist_name
                        + " | osu!taiko"
                        + " | " + acc_miss + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
        elif split_msg[0] == "with":
            # checks for former acm data if any
            if not osu_user.last_kwargs:
                acm_data = False
            else:
                acm_data = osu_user.last_kwargs

            all_mods = slider.Mod.parse('nfezhdhrfl')

            # reads args of message
            mods = slider.Mod.parse(split_msg[1]) & all_mods

            # sets mod names for output and checks if no args were passed
            if mods & 1 == 1:
                mods_name += "NF"
            if mods & 2 == 2:
                mods_name += "EZ"
            if mods & 8 == 8:
                mods_name += "HD"
            if mods & 16 == 16:
                mods_name += "HR"
            if mods & 1024 == 1024:
                mods_name += "FL"
            if mods == 0:
                return bot.msg(e.source.nick, "These mods are not supported yet!")

            osu_user.last_mod = mods
            if mode == 2:  # hd and fl
                if mods & ~slider.Mod.parse('hdfl'):
                    return bot.msg(e.source.nick, "These mods are not supported yet!")

                if acm_data:
                    acc, combo, miss = acm_data
                else:
                    acc, combo, miss = (100, beatmap_data_api.max_combo, 0)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode, acc=acc,
                                                  player_combo=combo, miss=miss, mods=mods)),)
                acc_combo_miss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " AR" + str(beatmap_data.approach_rate) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                return bot.msg(e.source.nick, artist_name
                               + " | osu!catch"
                               + " | " + acc_combo_miss + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
            elif mode == 3:  # nf and ez only
                if mods & ~slider.Mod.parse('nfez'):
                    return bot.msg(e.source.nick, "These mods are not supported yet!")

                if acm_data:
                    acc, score = acm_data
                else:
                    acc, score = (100, 1000000)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=acc, score=score,
                                                  mods=mods)),)
                acc_score = str(acc) + "% " + str(score) + " " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " " + str(Osu.key_count(beatmap_data)) + "key" \
                            + " OBJ" + str(len(beatmap_data.hit_objects))
                return bot.msg(e.source.nick, artist_name
                               + " | osu!mania"
                               + " | " + acc_score + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
            elif mode == 1:  # all mods as of now
                if acm_data:
                    acc, miss = acm_data
                else:
                    acc, miss = (100, 0)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode, acc=acc, miss=miss,
                                                  mods=mods)),)
                acc_miss = str(acc) + "% " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                    + "* " + bm_time \
                    + " OD" + str(beatmap_data.overall_difficulty) \
                    + " MAX" + str(beatmap_data_api.max_combo)
                return bot.msg(e.source.nick, artist_name
                               + " | osu!taiko"
                               + " | " + acc_miss + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def recommend(self, osu_user, bot, e):
        # https://github.com/Tyrrrz/OsuHelper/blob/master/OsuHelper/Services/RecommendationService.cs#L34

        def iterate_maps_callback(y):
            _temp_list.extend(y)
            finish_deferred.append(0)
            if len(finish_deferred) % 5 == 0:
                logger.debug(f"finished: {len(finish_deferred)} / {len(top_plays)}")
                bot.msg(e.source.nick, f"finished: {len(finish_deferred)} / {len(top_plays)}")
            if len(finish_deferred) == len(top_plays):
                _temp.update(_temp_list)
                osu_user.recommendations = recommendations = OrderedDict(islice(OrderedDict(sorted(_temp.items(), key=operator.itemgetter(1), reverse=True)).items(), 200))
                print(recommendations)
                bot.msg(e.source.nick, "done")

        def get_rec_from_map(i):
            client = cmd.osu_api_client.copy()
            beatmap = client.beatmap(beatmap_id=i.beatmap_id)
            start_deferred.append(0)
            if len(start_deferred) % 5 == 0:
                logger.debug(f"started: {len(start_deferred)} / {len(top_plays)}")
                bot.msg(e.source.nick, f"started: {len(start_deferred)} / {len(top_plays)}")
            logger.debug(f"{beatmap.title} [{beatmap.version}] id: {beatmap.beatmap_id}")
            # map top plays
            high_scores = sorted(client.beatmap_best(beatmap_id=i.beatmap_id, game_mode=game_mode),
                                 key=lambda x: abs(x.pp - i.pp))[:20]
            # through map top plays
            total_scores = []
            for j in high_scores:
                user_high_scores = sorted(
                    [k for k in client.user_best(user_id=j.user_id, game_mode=game_mode)
                     if (k.rank == "S" or k.rank == "X" or k.rank == "SH" or k.rank == "XH") and
                     (pp_limit_lower <= k.pp <= pp_limit_upper)],
                    key=lambda x: abs(x.pp - i.pp))[:20]
                total_scores.extend([k.beatmap_id for k in user_high_scores])
            return total_scores

        def iterate_map():
            # through own top plays
            for i in top_plays:

                # single thread
                # iterate_maps_callback(get_rec_from_map(i))

                # multi-thread
                d = threads.deferToThread(get_rec_from_map, i)
                d.addCallback(iterate_maps_callback)

        if osu_user.recommendations:
            pass

        # progress tracker (I was lazy, OK?)
        start_deferred = []
        finish_deferred = []

        _temp_list = []
        _temp = Counter()

        cmd = self.cmd
        game_mode = slider.GameMode(osu_user.preferences[e.source.nick].mode)
        osu_user.user_client = cmd.osu_api_client.user(user_name=e.source.nick, game_mode=game_mode)

        top_plays = osu_user.user_client.high_scores(limit=30)
        osu_user.top_plays[osu_user.preferences[e.source.nick].mode] = top_plays
        assert len(top_plays) > 0

        pp_list = [i.pp for i in top_plays]
        pp_limit_lower = sum(pp_list) / float(len(pp_list))
        pp_limit_upper = pp_limit_lower*1.25
        bot.msg(e.source.nick, "{:.2f}pp to {:.2f}pp".format(pp_limit_upper, pp_limit_lower))

        try:
            iterate_map()
        except:
            logger.exception("Rec Exception")
            bot.msg(e.source.nick, "RecommendError: Unknown")

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @staticmethod
    def calculate_pp(osu_b_data, osu_b_data_api, mode, mods=0, acc=100.0, **kwargs):
        if mode == 2:
            r = Osu.__CatchTheBeat()
        elif mode == 3:
            r = Osu.__Mania()
        elif mode == 1:
            r = Osu.__Taiko()
        else:
            return -1
        return r.calculate_pp(mods=mods, osu_b_data=osu_b_data, osu_b_data_api=osu_b_data_api, acc=acc, **kwargs)

    class __CatchTheBeat:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, player_combo=0, miss=0, mods=0):
            stars = float(osu_b_data_api.star_rating)
            max_combo = int(osu_b_data.max_combo)
            player_combo = int(osu_b_data.max_combo) if player_combo == 0 else player_combo
            ar = float(osu_b_data.approach_rate)

            final_pp = pow(((5 * max(1.0, stars / 0.0049)) - 4), 2) / 100000
            final_pp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (math.log(max_combo / 3000.0, 10) * 0.5
                                                                     if max_combo > 3000 else 0.0)
            final_pp *= pow(0.97, miss)
            final_pp *= pow(player_combo / max_combo, 0.8)
            if ar > 9:
                final_pp *= 1 + 0.1 * (ar - 9.0)
            elif ar < 8:
                final_pp *= 1 + 0.025 * (8.0 - ar)
            else:
                pass
            final_pp *= pow(acc / 100, 5.5)

            try:
                if mods & 8 == 8:
                    final_pp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
                elif mods & 1024 == 1024:
                    final_pp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (
                        math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
            except:
                pass

            return float(round(final_pp, 3))

    class __Mania:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, score=1000000, mods=0):
            #  Thanks Error- for the formula
            stars = float(osu_b_data_api.star_rating)
            od = float(osu_b_data.overall_difficulty)
            object_count = len(osu_b_data.hit_objects)

            perfect_window = 64 - 3 * od
            strain1 = math.pow(5 * max(1.0, stars / 0.0825) - 4, 3) / 110000
            strain2 = 1 + 0.1 * min(1.0, object_count / 1500)
            base_strain = strain2 * strain1
            strain_multiplier = (score / 500000 * 0.1 if score < 500000 else
                                 ((score - 500000) / 100000 * 0.2 + 0.1 if score < 600000 else
                                  ((score - 600000) / 100000 * 0.35 + 0.3 if score < 700000 else
                                   ((score - 700000) / 100000 * 0.2 + 0.65 if score < 800000 else
                                    ((score - 800000) / 100000 * 0.1 + 0.85 if score < 900000 else
                                     ((score - 900000) / 100000 * 0.05 + 0.95))))))
            acc_factor = math.pow(
                math.pow((150 / perfect_window) * math.pow(acc / 100, 16), 1.8) * 2.5 *
                min(1.15, math.pow(object_count / 1500, 0.3)), 1.1)
            strain_factor = math.pow(base_strain * strain_multiplier, 1.1)
            final_pp = math.pow(acc_factor + strain_factor, 1 / 1.1) * 1.1
            try:
                if mods & 2 == 2:
                    final_pp *= 0.5
                elif mods & 1 == 1:
                    final_pp *= 0.9
                else:
                    final_pp *= 1.1
            except:
                final_pp *= 1.1

            return float(round(final_pp, 3))

    class __Taiko:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, miss=0, mods=0):
            stars = float(osu_b_data_api.star_rating)
            max_combo = int(osu_b_data.max_combo)
            od = float(osu_b_data.overall_difficulty)
            perfect_hits = max_combo - miss

            try:
                if mods & 2 == 2:
                    od *= 0.5
                elif mods & 16 == 16:
                    od *= 1.4
                else:
                    pass
            except:
                pass

            max_od = 20
            min_od = 50
            result = min_od + (max_od - min_od) * od / 10
            result = math.floor(result) - 0.5
            perfect_window = round(result, 2)

            strain = (math.pow(max(float(1), stars / 0.0075) * 5 - 4, 2) / 100000) * \
                     (min(float(1), max_combo / 1500) * 0.1 + 1)
            strain *= math.pow(0.985, miss)
            strain *= min(math.pow(perfect_hits, 0.5) / math.pow(max_combo, 0.5), 1)
            strain *= acc / 100
            acc_factor = math.pow(150 / perfect_window, 1.1) * math.pow(acc / 100, 15) * 22
            acc_factor *= min(math.pow(max_combo / 1500, 0.3), 1.15)

            mod_multiplier = 1.1
            try:
                if mods & 8 == 8:
                    mod_multiplier *= 1.1
                    strain *= 1.025
                elif mods & 1 == 1:
                    mod_multiplier *= 0.9
                elif mods & 1024 == 1024:
                    strain *= 1.05 * min(float(1), max_combo / 1500) * 0.1 + 1
                else:
                    pass
            except:
                pass
            final_pp = math.pow(math.pow(strain, 1.1) + math.pow(acc_factor, 1.1), 1.0 / 1.1) * mod_multiplier
            return float(round(final_pp, 3))
