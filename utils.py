import logging
import logging.config
from functools import wraps
import re
import urllib.parse
import json
import pathlib
import time
import box

import sqlite3

import math
import slider

logging.config.fileConfig('logging.conf')
logger = logging.getLogger()


def is_owner():
    def is_owner_deco(f):
        wraps(f)

        def wrapper(*args, **kwargs):
            self, bot, c, e = args
            if e.source.nick == self.Config.config.main.owner:
                f(*args, **kwargs)
            else:
                c.privmsg(e.source.nick, "You do not have the permissions to run this command!")
        return wrapper
    return is_owner_deco


def command(remove_cmd=False):
    def command_deco(f):
        wraps(f)

        def wrapper(*args, **kwargs):
            self, bot, c, e = args
            try:
                if remove_cmd:
                    e.arguments[0] = e.arguments[0][len(bot.Config.config.main.prefix) + len(f.__name__) + 1:]
                    args = self, bot, c, e
                    f(*args, **kwargs)
                else:
                    f(*args, **kwargs)
            except IndexError as exc:
                c.privmsg(e.source.nick, "No arguments were passed.")
                logger.exception("Argument Exception")
            except Exception as exc:
                c.privmsg(e.source.nick, "A general error has occurred. Error: " + type(exc).__name__)
                logger.exception("General Exception")
        return wrapper
    return command_deco


class Config:
    def __init__(self, conf_filename):
        self.config = box.Box(json.load(open(pathlib.Path("./" + conf_filename), "r")))


class Utils:
    @staticmethod
    def isfloat(value):
        try:
            float(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def check_user_in_db(name, db, msg_type):
        userdb = sqlite3.connect(db)
        upcur = userdb.cursor()
        if msg_type == "ftm":
            upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
            if upcur.fetchone() is None:
                upcur.execute("INSERT INTO userdb (user) VALUES (?)", (name,))
                userdb.commit()
                userdb.close()
                return False
            else:
                userdb.close()
                return True
        elif msg_type == "um":
            upcur.execute("SELECT info FROM userdb WHERE user=?", (name,))
            test = upcur.fetchone()[0]
            if test is None:
                upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
                test = upcur.fetchone()[0]
                if test is None:
                    upcur.execute("INSERT INTO userdb (user, info) VALUES (?, ?)", (name, 1))
                else:
                    upcur.execute("UPDATE userdb SET info = ? WHERE user = ?", (1, name))
                userdb.commit()
                userdb.close()
                return False
            else:
                userdb.close()
                return True

    @staticmethod
    def check_mode_in_db(name, db, beatmap_data, np=False):
        sent = []
        userdb = sqlite3.connect(db)
        upcur = userdb.cursor()
        if int(beatmap_data.mode) != 0:
            mode = int(beatmap_data.mode)
            if np:
                upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
                modedb = upcur.fetchone()
                if modedb is None:
                    sent.append("Automatically setting mode to " + slider.GameMode(mode).name + "... " +
                                "use \"!set mode [catch|mania|taiko]\" to change")
                    userdb.commit()
                    Utils.set_pref(name, 'userpref.db', mode)
            return mode, sent
        else:
            upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
            modedb = upcur.fetchone()
            if modedb is None:
                sent.append("Please set a mode with !set mode [catch|mania|taiko]")
                return -1, sent
            else:
                mode = modedb[1]
                if mode is None:
                    sent.append("Please set a mode with !set mode [catch|mania|taiko]")
                    return -1, sent
                userdb.commit()
                return mode, sent

    @staticmethod
    def set_pref(name, db, mode):
        userdb = sqlite3.connect('userpref.db')
        upcur = userdb.cursor()
        upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
        if upcur.fetchone() is None:
            upcur.execute("INSERT INTO userdb (user, mode) VALUES (?,?)", (name, mode))
        else:
            upcur.execute("UPDATE userdb SET mode = ? WHERE user = ?", (mode, name))
        userdb.commit()
        userdb.close()


class Commands:
    def __init__(self, config):
        self.Config = config

    @is_owner()
    @command()
    def disconnect(self, bot, c, e):
        bot.disconnect()

    @is_owner()
    @command()
    def die(self, bot, c, e):
        bot.die()

    @is_owner()
    @command()
    def test(self, bot, c, e):
        c.privmsg(e.source.nick, str(bot.users[e.source.nick].__dict__))
        logger.debug(str(bot.users[e.source.nick].last_beatmap[1].__dict__))

    @is_owner()
    @command()
    def resetupdate(self, bot, c, e):
        userdb = sqlite3.connect("userpref.db")
        upcur = userdb.cursor()
        upcur.execute('UPDATE userdb SET info = ?', (None,))
        userdb.commit()
        userdb.close()

    @is_owner()
    @command()
    def resetosu(self, bot, c, e):  # incur this command when you change anything in the Osu class and you don't want a
        bot.users = {}              # reload

    @is_owner()
    @command()
    def sortdb(self, bot, c, e):
        userdb = sqlite3.connect('userpref.db')
        upcur = userdb.cursor()
        upcur.execute("CREATE TABLE IF NOT EXISTS userdbsorted (user INT PRIMARY KEY, mode INT, info INT)")
        userdb.commit()
        upcur.execute("INSERT INTO userdbsorted (user, mode, info) SELECT * FROM userdb ORDER BY user Collate NOCASE")
        upcur.execute("DROP TABLE userdb")
        upcur.execute("ALTER TABLE userdbsorted RENAME TO userdb")
        userdb.commit()
        c.privmsg(e.source.nick, "Sorted database.")

    @command()
    def help(self, bot, c, e):
        c.privmsg(e.source.nick, "Need help? Check [https://github.com/de-odex/FruityBot/wiki the wiki] "
                                 "for commands.")

    h = help

    @command()
    def uptime(self, bot, c, e):
        c.privmsg(e.source.nick, time.strftime("%H;%M;%S", time.gmtime(time.time() - bot.start_time)) + " since start.")

    @command()
    def time(self, bot, c, e):
        c.privmsg(e.source.nick, "Local time: " + time.strftime("%B %d %H:%M:%S", time.localtime(time.time())))

    @command(remove_cmd=True)
    def set(self, bot, c, e):
        split_msg2 = e.arguments[0].split()

        if split_msg2[0] == "mode":
            if split_msg2[1].lower() in ["catch", "ctb", "c", "2"]:
                mode = 2
            elif split_msg2[1].lower() in ["mania", "m", "3"]:
                mode = 3
            elif split_msg2[1].lower() in ["taiko", "t", "1"]:
                mode = 1
            elif split_msg2[1].lower() in ["standard", "std", "osu", "o", "0"]:
                c.privmsg(e.source.nick, "Please message Tillerino for standard pp predictions!")
                return
            else:
                c.privmsg(e.source.nick, "Invalid command")
                return
            Utils.set_pref(e.source.nick, 'userpref.db', mode)
            c.privmsg(e.source.nick, "Set <" + split_msg2[0] + "> to <" + split_msg2[1] + ">")
        else:
            return c.privmsg(e.source.nick, "Invalid command")

    # Osu! ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @command()
    def recommend(self, bot, c, e):
        c.privmsg(e.source.nick, "Still under construction...")

    cmd_r = recommend

    @command()
    def np(self, bot, c, e):
        if e.type == "action":
            if e.source.nick in bot.users:
                user = bot.users[e.source.nick]
                user.np(c, e)
            else:
                user = Osu(e.source.nick, bot)
                bot.users[e.source.nick] = user
                user.np(c, e)
        else:
            c.privmsg(e.source.nick, "Please use \"/np\"!")

    @command()
    def cmd_with(self, bot, c, e):
        if e.source.nick in bot.users:
            user = bot.users[e.source.nick]
            user.acm_mod(c, e)
        else:
            return c.privmsg(e.source.nick, "You haven't /np'd me anything yet!")


class Osu:
    def __init__(self, user, bot):
        self.user = user
        self.bot = bot  # use self.bot.osu_library to get the library, to survive reloads
        self.last_beatmap = False
        self.last_mod = False
        self.last_kwargs = False

    @staticmethod
    def keycount(beatmap):
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

    @staticmethod
    def send(c, e, sent):
        for i in list(sent):
            c.privmsg(e.source.nick, i)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def np(self, c, e):
        sent = []
        self.last_mod = False
        self.last_kwargs = False
        link = urllib.parse.urlparse(re.findall(
            'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            e.arguments[0])[0])
        beatmap_id = link.path.split("/")
        if beatmap_id[1] != "b":
            sent.append("This is a beatmapset, not a beatmap")
            return Osu.send(c, e, sent)
        beatmap_id = beatmap_id[2].split("&")[0]
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        beatmap_data = self.bot.osu_library.lookup_by_id(beatmap_id, download=True, save=True)
        beatmap_data_api = self.bot.osu_api_client.beatmap(beatmap_id=beatmap_id, include_converted_beatmaps=True)
        if not beatmap_data_api:
            raise Exception  # ModeError

        mode, send_queue = Utils.check_mode_in_db(e.source.nick, 'userpref.db', beatmap_data, np=True)
        Osu.send(c, e, send_queue)

        if mode == -1:
            return

        beatmap_data_api = self.bot.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                           include_converted_beatmaps=True,
                                                           game_mode=slider.game_mode.GameMode(mode))

        if beatmap_data_api.max_combo is None and mode is not 3:
            beatmap_data_api = self.bot.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                               include_converted_beatmaps=True)

        self.last_beatmap = (beatmap_data, beatmap_data_api, mode, beatmap_id)
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
        bm_time = time.strftime("%M:%S", time.gmtime(int(beatmap_data_api.hit_length.seconds)))

        if mode == 2:
            pp_vals = list(str(Osu.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=i)) for i in
                       [100, 99.5, 99, 98.5])
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " AR" + str(beatmap_data.approach_rate) \
                        + " MAX" + str(beatmap_data_api.max_combo)
            sent.append(artist_name
                        + " | osu!catch"
                        + " | SS: " + pp_vals[0] + "pp"
                        + " | 99.5% FC: " + pp_vals[1] + "pp"
                        + " | 99% FC: " + pp_vals[2] + "pp"
                        + " | 98.5% FC: " + pp_vals[3] + "pp"
                        + " | " + end_props)
        elif mode == 3:
            pp_vals = (str(Osu.calculatepp(beatmap_data, beatmap_data_api, mode=mode)),
                       str(Osu.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=99, score=970000)),
                       str(Osu.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=97, score=900000)))
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " OD" + str(beatmap_data.overall_difficulty) \
                        + " " + str(Osu.keycount(beatmap_data)) + "key" \
                        + " OBJ" + str(len(beatmap_data.hit_objects))
            sent.append(artist_name
                        + " | osu!mania"
                        + " | SS: " + pp_vals[0] + "pp"
                        + " | 99% 970k: " + pp_vals[1] + "pp"
                        + " | 97% 900k: " + pp_vals[2] + "pp"
                        + " | " + end_props)
        elif mode == 1:
            pp_vals = list(str(Osu.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=i)) for i in [100, 99, 98])
            end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                        + "* " + bm_time \
                        + " OD" + str(beatmap_data.overall_difficulty) \
                        + " MAX" + str(beatmap_data_api.max_combo)
            sent.append(artist_name
                        + " | osu!taiko"
                        + " | SS: " + pp_vals[0] + "pp"
                        + " | 99% FC: " + pp_vals[1] + "pp"
                        + " | 98% FC: " + pp_vals[2] + "pp"
                        + " | " + end_props)
        return Osu.send(c, e, sent)

    def acm_mod(self, c, e):
        sent = []
        mods_name = ""

        beatmap_data, beatmap_data_api, mode_api, beatmap_id = self.last_beatmap

        mode, send_queue = Utils.check_mode_in_db(e.source.nick, 'userpref.db', beatmap_data)
        Osu.send(c, e, send_queue)

        if mode_api != mode:
            beatmap_data_api = self.bot.osu_api_client.beatmap(beatmap_id=beatmap_id,
                                                           include_converted_beatmaps=True,
                                                           game_mode=slider.game_mode.GameMode(mode))

        max_combo = int(beatmap_data_api.max_combo) if beatmap_data_api.max_combo is not None else "err"
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
        bm_time = time.strftime("%M:%S", time.gmtime(int(beatmap_data_api.hit_length.seconds)))
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if e.arguments[0].split()[0] == "!acc":

            # checks for former mod data if any
            if not self.last_mod:
                mods = 0
            else:
                mods = self.last_mod

            # reads args of message
            acc = combo = miss = score = 'hi'
            for i in split_msg:
                if Utils.isfloat(i):
                    acc = i
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
                if combo == 'hi':
                    combo = int(beatmap_data_api.max_combo)
                if miss == 'hi':
                    miss = 0
                try:
                    miss = int(miss)
                    if miss < max_combo or miss >= 0:
                        miss = miss
                    else:
                        raise SyntaxError
                except:
                    sent.append("You MISSed something there")
                    return sent
                try:
                    combo = int(combo)
                    if 0 <= combo <= max_combo:
                        combo = combo
                    else:
                        raise SyntaxError
                except:
                    sent.append("You made a mistake with your combo!")
                    return sent
                try:
                    acc = float(acc)
                    if 0.0 <= acc <= 100.0:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    sent.append("Check your accuracy again, please")
                    return sent

                acm_data_s[name] = [acc, combo, miss]
                pp_vals = (str(calc.calculatepp(beatmap_data,
                                                beatmap_data_api, mode, acc=acc,
                                                max_player_combo=combo, miss=miss,
                                                mods=mods)),)
                acccombomiss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " AR" + str(beatmap_data.approach_rate) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                sent.append(artist_name \
                            + " | osu!catch" \
                            + " | " + acccombomiss + ": " \
                            + pp_vals[0] + "pp" \
                            + " | " + end_props)
            elif mode == 3:
                try:
                    score = int(score)
                    if 1000000 >= score >= 0:
                        score = score
                    else:
                        raise SyntaxError
                except:
                    sent.append("You messed up your score there...")
                    return sent
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    sent.append("Check your accuracy again, please")
                    return sent

                acm_data_s[name] = [acc, score]
                pp_vals = (str(calc.calculatepp(beatmap_data,
                                                beatmap_data_api, mode=mode, acc=acc,
                                                score=score, mods=mods)),)
                accscore = str(acc) + "% " + str(score) + " " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " " + str(calc.keycount(beatmap_data)) + "key" \
                            + " OBJ" + str(len(beatmap_data.hit_objects))
                sent.append(artist_name \
                            + " | osu!mania" \
                            + " | " + accscore + ": " \
                            + pp_vals[0] + "pp" \
                            + " | " + end_props)
            elif mode == 1:
                try:
                    miss = int(miss)
                    if miss < max_combo or miss >= 0:
                        miss = miss
                    else:
                        raise SyntaxError
                except:
                    sent.append("You MISSed something there")
                    return sent
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    sent.append("Check your accuracy again, please")
                    return sent

                acm_data_s[name] = [acc, miss]
                pp_vals = (str(calc.calculatepp(beatmap_data,
                                                beatmap_data_api, mode=mode, acc=acc,
                                                miss=miss, mods=mods)),)
                accmiss = str(acc) + "% " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                sent.append(artist_name \
                            + " | osu!taiko" \
                            + " | " + accmiss + ": " \
                            + pp_vals[0] + "pp" \
                            + " | " + end_props)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @staticmethod
    def calculatepp(osubdata, osubdata_api, mode, mods=0, acc=100, **kwargs):
        if mode == 2:
            r = Osu.__CatchTheBeat()
        elif mode == 3:
            r = Osu.__Mania()
        elif mode == 1:
            r = Osu.__Taiko()
        return r.calculatepp(mods=mods, osubdata=osubdata, osubdata_api=osubdata_api, acc=acc, **kwargs)

    class __CatchTheBeat:
        @staticmethod
        def calculatepp(osubdata, osubdata_api, acc=100, player_combo=0, miss=0, mods=0):
            stars = float(osubdata_api.star_rating)
            max_combo = int(osubdata.max_combo)
            player_combo = int(osubdata.max_combo) if player_combo == 0 else player_combo
            ar = float(osubdata.approach_rate)

            finalpp = pow(((5 * max(1.0, stars / 0.0049)) - 4), 2) / 100000
            finalpp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) + \
                       (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0)
            finalpp *= pow(0.97, miss)
            finalpp *= pow(player_combo / max_combo, 0.8)
            if ar > 9:
                finalpp *= 1 + 0.1 * (ar - 9.0)
            elif ar < 8:
                finalpp *= 1 + 0.025 * (8.0 - ar)
            else:
                pass
            finalpp *= pow(acc / 100, 5.5)

            try:
                if mods & 8 == 8:
                    finalpp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
                elif mods & 1024 == 1024:
                    finalpp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (
                        math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
            except:
                pass

            return float(round(finalpp, 3))

    class __Mania:
        @staticmethod
        def calculatepp(osubdata, osubdata_api, acc=100, score=1000000, mods=0):
            #  Thanks Error- for the formula
            stars = float(osubdata_api.star_rating)
            od = float(osubdata.overall_difficulty)
            objectcount = len(osubdata.hit_objects)
            if int(osubdata.mode) == 0:
                orig_keys = Osu.keycount(osubdata)
            else:
                orig_keys = osubdata.circle_size

            pfwdw = 64 - 3 * od
            strain1 = math.pow(5 * max(1, stars / 0.0825) - 4, 3) / 110000
            strain2 = 1 + 0.1 * min(1, objectcount / 1500)
            strainbase = strain2 * strain1
            strainmult = score / 500000 * 0.1 if score < 500000 else (
                (score - 500000) / 100000 * 0.2 + 0.1 if score < 600000 else (
                    (score - 600000) / 100000 * 0.35 + 0.3 if score < 700000 else (
                        (score - 700000) / 100000 * 0.2 + 0.65 if score < 800000 else (
                            (score - 800000) / 100000 * 0.1 + 0.85 if score < 900000 else (
                                (score - 900000) / 100000 * 0.05 + 0.95)))))
            accfinal = math.pow(
                math.pow((150 / pfwdw) * math.pow(acc / 100, 16), 1.8) * 2.5 *
                min(1.15, math.pow(objectcount / 1500, 0.3)), 1.1)
            strainfinal = math.pow(strainbase * strainmult, 1.1)
            finalpp = math.pow(accfinal + strainfinal, 1 / 1.1) * 1.1
            try:
                if mods & 2 == 2:
                    finalpp *= 0.5
                elif mods & 1 == 1:
                    finalpp *= 0.9
                else:
                    finalpp *= 1.1
            except:
                finalpp *= 1.1

            return float(round(finalpp, 3))

    class __Taiko:
        @staticmethod
        def calculatepp(osubdata, osubdata_api, acc=100, miss=0, mods=0):
            stars = float(osubdata_api.star_rating)
            max_combo = int(osubdata.max_combo)
            od = float(osubdata.overall_difficulty)
            pfhit = max_combo - miss

            try:
                if mods & 2 == 2:
                    od *= 0.5
                elif mods & 16 == 16:
                    od *= 1.4
                else:
                    pass
            except:
                pass

            maxod = 20
            minod = 50
            result = minod + (maxod - minod) * od / 10
            result = math.floor(result) - 0.5
            pfwdw = round(result, 2)

            strain = (math.pow(max(float(1), stars / 0.0075) * 5 - 4, 2) / 100000) * \
                     (min(float(1), max_combo / 1500) * 0.1 + 1)
            strain *= math.pow(0.985, miss)
            strain *= min(math.pow(pfhit, 0.5) / math.pow(max_combo, 0.5), 1)
            strain *= acc / 100
            accfinal = math.pow(150 / pfwdw, 1.1) * math.pow(acc / 100, 15) * 22
            accfinal *= min(math.pow(max_combo / 1500, 0.3), 1.15)

            modmult = 1.1
            try:
                if mods & 8 == 8:
                    modmult *= 1.1
                    strain *= 1.025
                elif mods & 1 == 1:
                    modmult *= 0.9
                elif mods & 1024 == 1024:
                    strain *= 1.05 * min(float(1), max_combo / 1500) * 0.1 + 1
                else:
                    pass
            except:
                pass
            finalpp = math.pow(math.pow(strain, 1.1) + math.pow(accfinal, 1.1), 1.0 / 1.1) * modmult
            return float(round(finalpp, 3))
