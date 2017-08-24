#!/usr/bin/env python3.6

# See LICENSE for details.

# twisted imports
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, threads, defer
from twisted.python import log

# system imports
import time
import sys
import re
import urllib
import traceback
import slider
import sqlite3
import os
import requests
import pathlib
import colorama
import random
import importlib

colorama.init(autoreset=True)

try:
    import config, calc, recommend
except ImportError:
    print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET +
          "No modules. Please re-download and make a config.py.")
    input()
    sys.exit()

# user database for settings
userdb = sqlite3.connect('userpref.db')
userdb.isolation_level = None
try:
    upcur = userdb.cursor()
    upcur.execute("BEGIN")
    upcur.execute("CREATE TABLE IF NOT EXISTS userdb (user INT PRIMARY KEY, mode INT)")
    upcur.execute("COMMIT")
except userdb.Error:
    print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET
          + "failed to create the database!")
    upcur.execute("ROLLBACK")

# Library creation if does not exist
libdir = pathlib.Path("./osulib")
libdir = libdir.absolute()

if not libdir.exists():
    os.makedirs(libdir)
    osu_library = slider.library.Library.create_db(libdir)
    print(colorama.Style.BRIGHT + "Created osu! library")
else:
    osu_library = slider.library.Library(libdir)

beatmap_data_s = {}
acm_data_s = {}
mod_data_s = {}


class ModeError(Exception):
    pass


class MsgError(Exception):
    pass


class NpError(Exception):
    pass


class AttrError(Exception):
    pass


class TopPlayError(Exception):
    pass


class ComboError(Exception):
    pass


class ProgramLogic:
    """An independent logic class (because separation of application and protocol logic is a good thing)."""

    def __init__(self, file):
        self.file = file
        self.repfile = open("reports.log", "a")
        self.UPDATE_MSG = \
            "eyo, its boterino here with an update ([https://aeverr.s-ul.eu/CpdBefOU sic]). " \
            "[https://discord.gg/2NjBpNa We have a Discord server]. ZeroDivisionError fixed."
        self.FIRST_TIME_MSG = \
            "Welcome, and thanks for using my bot! " \
            "Check out [https://github.com/de-odex/FruityBot/wiki the wiki] for commands. " \
            "!botreport to report a bug."
        self.osu_api_client = slider.client.Client(osu_library, config.api_key)

    def log(self, message):
        """Write a message to the file."""
        print(colorama.Style.BRIGHT + message)
        message = re.sub('\033\[\d+m', '', message)
        timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
        self.file.write('%s %s\n' % (timestamp, message))
        self.file.flush()

    def close(self):
        self.file.close()
        self.repfile.close()

    # my commands now :3

    def isfloat(self, value):
        try:
            float(value)
            return True
        except ValueError:
            return False

    def savetofile(self, msg, file):
        timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
        file.write('%s %s\n' % (timestamp, msg))
        file.flush()
        pass

    def report(self, msg):
        self.savetofile(msg, self.repfile)

    # message sending ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def sendstore(self, message, name, file1):
        cur_path = os.path.dirname(__file__)
        new_path = os.path.relpath('log\\', cur_path)
        fin_path = os.path.join(new_path, file1)
        temp = open(fin_path, "a")  # if file doesn't exist, make it
        temp.close()  # close file
        names_file = open(fin_path, "r")  # read file data
        all_names = names_file.read().splitlines()  # split to lines
        names_file.close()  # close reading, for writing
        if name not in all_names:
            names_file = open(fin_path, "a+")  # write file data
            names_file.write(name + "\n")  # write file data
            names_file.close()  # close file for resources
            return message
        else:
            return False

    def check_update(self, msg, user, file):
        x = self.sendstore(msg, user, file)
        if x:
            return x

    def setpref(self, message, name):
        split_msg = message.split("!set ")[1]
        split_msg2 = split_msg.split()

        if split_msg2[0] == "mode":
            if split_msg2[1].lower() == "catch":
                mode = 2
            elif split_msg2[1].lower() == "mania":
                mode = 3
            elif split_msg2[1].lower() == "taiko":
                mode = 1
            else:
                return "Invalid command"
            try:
                userdb = sqlite3.connect('userpref.db')
                upcur = userdb.cursor()
                upcur.execute("BEGIN")
                upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
                if upcur.fetchone() is None:
                    upcur.execute("INSERT INTO userdb (user, mode) VALUES (?,?)", (name, mode))
                else:
                    upcur.execute("UPDATE userdb SET mode = ? WHERE user = ?", (mode, name))
                upcur.execute("COMMIT")
            except userdb.Error:
                upcur.execute("ROLLBACK")
            return "Set <" + split_msg2[0] + "> to <" + split_msg2[1] + ">"
        else:
            return "Invalid command"

    def sendpp(self, message, name, ident="np"):
        try:
            global beatmap_data_s, mod_data_s, osu_library
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            if ident == "np":
                link = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                                  message)
                mod_data_s[name] = 0
                acm_data_s[name] = 0
                beatmap_id = urllib.parse.urlparse(link[0]).path.split("/")
                if beatmap_id[1] != "b":
                    return "This is a beatmapset, not a beatmap"
                beatmap_id = beatmap_id[2].split("&")[0]
                beatmap_data = osu_library.lookup_by_id(beatmap_id, download=True, save=True)
                beatmap_data_api = self.osu_api_client.beatmap(beatmap_id=beatmap_id, include_converted_beatmaps=True)
                if not beatmap_data_api:
                    raise ModeError

                # checks mode
                if int(beatmap_data.mode) != 0:
                    mode = int(beatmap_data.mode)
                else:
                    try:
                        userdb = sqlite3.connect('userpref.db')
                        upcur = userdb.cursor()
                        upcur.execute("BEGIN")
                        upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
                        modedb = upcur.fetchone()
                        if modedb is None:
                            return "Please set a mode with !set mode [catch|mania|taiko]"
                        else:
                            upcur.execute("SELECT mode FROM userdb WHERE user=?", (name,))
                            mode = modedb[1]
                            upcur.execute("COMMIT")
                    except userdb.Error:
                        upcur.execute("ROLLBACK")

                beatmap_data_api = self.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                               include_converted_beatmaps=True,
                                                               game_mode=slider.game_mode.GameMode(mode))

                if beatmap_data_api.max_combo is None and mode is not 3:
                    beatmap_data_api = self.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                                   include_converted_beatmaps=True)

                beatmap_data_s[name] = (beatmap_data, beatmap_data_api, mode, beatmap_id)
                artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
                bm_time = time.strftime("%M:%S", time.gmtime(int(beatmap_data_api.hit_length.seconds)))

                if mode == 2:
                    pp_vals = (str(calc.calculatepp(beatmap_data, beatmap_data_api, mode)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode, acc=99.5)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode, acc=99)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode, acc=98.5)))
                    end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                + "* " + bm_time \
                                + " AR" + str(beatmap_data.approach_rate) \
                                + " MAX" + str(beatmap_data_api.max_combo)
                    sent = artist_name \
                           + " | osu!catch" \
                           + " | SS: " + pp_vals[0] + "pp" \
                           + " | 99.5% FC: " + pp_vals[1] + "pp" \
                           + " | 99% FC: " + pp_vals[2] + "pp" \
                           + " | 98.5% FC: " + pp_vals[3] + "pp" \
                           + " | " + end_props
                elif mode == 3:
                    pp_vals = (str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=99, score=970000)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=97, score=900000)))
                    end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                + "* " + bm_time \
                                + " OD" + str(beatmap_data.overall_difficulty) \
                                + " " + str(calc.keycount(beatmap_data)) + "key" \
                                + " OBJ" + str(len(beatmap_data.hit_objects))
                    sent = artist_name \
                           + " | osu!mania" \
                           + " | SS: " + pp_vals[0] + "pp" \
                           + " | 99% 970k: " + pp_vals[1] + "pp" \
                           + " | 97% 900k: " + pp_vals[2] + "pp" \
                           + " | " + end_props
                elif mode == 1:
                    pp_vals = (str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=99)),
                               str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=98)))
                    end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                + "* " + bm_time \
                                + " OD" + str(beatmap_data.overall_difficulty) \
                                + " MAX" + str(beatmap_data_api.max_combo)
                    sent = artist_name \
                           + " | osu!taiko" \
                           + " | SS: " + pp_vals[0] + "pp" \
                           + " | 99% FC: " + pp_vals[1] + "pp" \
                           + " | 98% FC: " + pp_vals[2] + "pp" \
                           + " | " + end_props
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            elif ident == "acm" or ident == "mod" or ident == "key":
                mods_name = ""
                if name not in beatmap_data_s:
                    raise NpError

                beatmap_data, beatmap_data_api, mode_api, beatmap_id = beatmap_data_s[name]

                split_msg = message.split()
                del split_msg[0]
                if not split_msg:
                    raise MsgError

                # checks mode
                if int(beatmap_data.mode) != 0:
                    mode = int(beatmap_data.mode)
                else:
                    try:
                        userdb = sqlite3.connect('userpref.db')
                        upcur = userdb.cursor()
                        upcur.execute("BEGIN")
                        upcur.execute("SELECT * FROM userdb WHERE user=?", (name,))
                        modedb = upcur.fetchone()
                        if modedb is None:
                            return "Please set a mode with !set mode [catch|mania|taiko]"
                        else:
                            upcur.execute("SELECT mode FROM userdb WHERE user=?", (name,))
                            mode = modedb[1]
                            upcur.execute("COMMIT")
                    except userdb.Error:
                        upcur.execute("ROLLBACK")

                if mode_api != mode:
                    beatmap_data_api = self.osu_api_client.beatmap(beatmap_id=beatmap_id,
                                                                   include_converted_beatmaps=True,
                                                                   game_mode=slider.game_mode.GameMode(mode))

                max_combo = int(beatmap_data_api.max_combo) if beatmap_data_api.max_combo is not None else "err"
                artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
                bm_time = time.strftime("%M:%S", time.gmtime(int(beatmap_data_api.hit_length.seconds)))
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                if ident == "acm":

                    # checks for former mod data if any
                    if name not in mod_data_s:
                        mods = 0
                    else:
                        mods = mod_data_s[name]

                    # reads args of message
                    acc = combo = miss = score = 'hi'
                    for i in split_msg:
                        if self.isfloat(i):
                            acc = i
                        elif i.endswith(("x",)):
                            combo = i.rstrip("x")
                        elif i.endswith(("m",)):
                            miss = i.rstrip("m")
                        elif i.endswith(("s",)):
                            score = i.rstrip("s")
                        else:
                            pass

                    # checks if no args were passed
                    if acc == 'hi' and combo == 'hi' and miss == 'hi' and score == 'hi':
                        raise AttrError

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
                            return "You MISSed something there"
                        try:
                            combo = int(combo)
                            if 0 <= combo <= max_combo:
                                combo = combo
                            else:
                                raise SyntaxError
                        except:
                            return "You made a mistake with your combo!"
                        try:
                            acc = float(acc)
                            if 0.0 <= acc <= 100.0:
                                acc = acc
                            else:
                                raise SyntaxError
                        except:
                            return "Check your accuracy again, please"

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
                        sent = artist_name \
                               + " | osu!catch" \
                               + " | " + acccombomiss + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                    elif mode == 3:
                        try:
                            score = int(score)
                            if 1000000 >= score >= 0:
                                score = score
                            else:
                                raise SyntaxError
                        except:
                            return "You messed up your score there..."
                        try:
                            acc = float(acc)
                            if 0 <= acc <= 100:
                                acc = acc
                            else:
                                raise SyntaxError
                        except:
                            return "Check your accuracy again, please"

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
                        sent = artist_name \
                               + " | osu!mania" \
                               + " | " + accscore + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                    elif mode == 1:
                        try:
                            miss = int(miss)
                            if miss < max_combo or miss >= 0:
                                miss = miss
                            else:
                                raise SyntaxError
                        except:
                            return "You MISSed something there"
                        try:
                            acc = float(acc)
                            if 0 <= acc <= 100:
                                acc = acc
                            else:
                                raise SyntaxError
                        except:
                            return "Check your accuracy again, please"

                        acm_data_s[name] = [acc, miss]
                        pp_vals = (str(calc.calculatepp(beatmap_data,
                                                        beatmap_data_api, mode=mode, acc=acc,
                                                        miss=miss, mods=mods)),)
                        accmiss = str(acc) + "% " + str(miss) + "miss " + mods_name
                        end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                    + "* " + bm_time \
                                    + " OD" + str(beatmap_data.overall_difficulty) \
                                    + " MAX" + str(beatmap_data_api.max_combo)
                        sent = artist_name \
                               + " | osu!taiko" \
                               + " | " + accmiss + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                elif ident == "mod":

                    # checks for former acm data if any
                    if name not in acm_data_s:
                        pass
                    else:
                        acm_data = acm_data_s[name]
                    mods = 0

                    # reads args of message
                    if split_msg[0].lower().find("hd") != -1:
                        mods += 8
                    if split_msg[0].lower().find("fl") != -1:
                        mods += 1024
                    if split_msg[0].lower().find("ez") != -1:
                        mods += 2
                    if split_msg[0].lower().find("nf") != -1:
                        mods += 1
                    if split_msg[0].lower().find("hr") != -1:
                        mods += 16

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
                        return "These mods are not supported yet!"

                    mod_data_s[name] = mods
                    if mode == 2:  # hd and fl only
                        if mods & 1 == 1:
                            return "These mods are not supported yet!"
                        if mods & 2 == 2:
                            return "These mods are not supported yet!"
                        if mods & 16 == 16:
                            return "These mods are not supported yet!"

                        if acm_data in locals():
                            acc, combo, miss = acm_data
                        else:
                            acc, combo, miss = (100, beatmap_data_api.max_combo, 0)
                        pp_vals = (str(calc.calculatepp(beatmap_data,
                                                        beatmap_data_api, mode, acc=acc,
                                                        combo=combo, miss=miss,
                                                        mods=mods)))
                        acccombomiss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                        end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                    + "* " + bm_time \
                                    + " AR" + str(beatmap_data.approach_rate) \
                                    + " MAX" + str(beatmap_data_api.max_combo)
                        sent = artist_name \
                               + " | osu!catch" \
                               + " | " + acccombomiss + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                    elif mode == 3:  # nf and ez only
                        if mods & 8 == 8:
                            return "These mods are not supported yet!"
                        if mods & 1024 == 1024:
                            return "These mods are not supported yet!"
                        if mods & 16 == 16:
                            return "These mods are not supported yet!"

                        if acm_data in locals():
                            acc, score = acm_data
                        else:
                            acc, score = (100, 1000000)
                        pp_vals = (
                            str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=acc, score=score,
                                                 mods=mods)),)
                        accscore = str(acc) + "% " + str(score) + " " + mods_name
                        end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                    + "* " + bm_time \
                                    + " OD" + str(beatmap_data.overall_difficulty) \
                                    + " " + str(calc.keycount(beatmap_data)) + "key" \
                                    + " OBJ" + str(len(beatmap_data.hit_objects))
                        sent = artist_name \
                               + " | osu!mania" \
                               + " | " + accscore + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                    elif mode == 1:  # all mods as of now
                        if acm_data in locals():
                            acc, miss = acm_data
                        else:
                            acc, miss = (100, 0)
                        pp_vals = (str(calc.calculatepp(beatmap_data, beatmap_data_api, mode, acc=acc, miss=miss,
                                                        mods=mods)),)
                        accmiss = str(acc) + "% " + str(miss) + "miss " + mods_name
                        end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                    + "* " + bm_time \
                                    + " OD" + str(beatmap_data.overall_difficulty) \
                                    + " MAX" + str(beatmap_data_api.max_combo)
                        sent = artist_name \
                               + " | osu!taiko" \
                               + " | " + accmiss + ": " \
                               + pp_vals[0] + "pp" \
                               + " | " + end_props
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                elif ident == "key":

                    # checks for former mod data if any
                    if name not in mod_data_s:
                        mods = 0
                    else:
                        mods = mod_data_s[name]

                    # reads args of message
                    keys = re.sub('\D', '', split_msg[0])
                    keys = int(keys)
                    if not 1 < keys < 9 and  self.isfloat(keys):
                        return "You gave an invalid amount of keys!"

                    # sets key names for output
                    key_name = str(keys)

                    if mode == 2:
                        return "This mode doesn't have a keys modifier!"
                    elif mode == 3:
                        pp_vals = (
                            str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode,
                                                 mods=mods, keys=keys)),
                            str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=99, score=970000,
                                                 mods=mods, keys=keys)),
                            str(calc.calculatepp(beatmap_data, beatmap_data_api, mode=mode, acc=97, score=900000,
                                                 mods=mods, keys=keys)))

                        end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                                    + "* " + bm_time \
                                    + " OD" + str(beatmap_data.overall_difficulty) \
                                    + " " + key_name + "key" \
                                    + " OBJ" + str(len(beatmap_data.hit_objects))
                        sent = artist_name \
                               + " | osu!mania" \
                               + " | SS: " + pp_vals[0] + "pp" \
                               + " | 99% 970k: " + pp_vals[1] + "pp" \
                               + " | 97% 900k: " + pp_vals[2] + "pp" \
                               + " | " + end_props
                    elif mode == 1:
                        return "This mode doesn't have a keys modifier!"
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            return sent
        except IndexError:
            return "There seems to be no link in your /np... Is this a beatmap you made?"
        except ModeError:
            return "This map doesn\'t seem to have this mode... Somehow I haven't noticed so."
        except MsgError:
            return "Somehow your message got lost in my head... Send it again? (No arguments)"
        except NpError:
            return "You haven't /np'd me anything yet!"
        except AttrError:
            return "Do it like me, \"!acc 95 200x 1m\". Or something, I dunno. " \
                   "See [https://github.com/de-odex/FruityBot/wiki the wiki!]"
        except ComboError:
            return "Something's up, or I guess in this case, down, with your combo."
        except requests.exceptions.HTTPError as exc:
            if 500 <= exc.response.status_code <= 599:
                sendpp(message, name, ident)
                return "If you're seeing this message, that means my bot broke somehow. Error:OsuApi"
            else:
                print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET +
                      " internet, " + str(e.response.status_code))
                sendpp(message, name, ident)
                return "If you're seeing this message, that means my bot broke somehow. Error:FrtSrv"
        except:
            rdm = random.randint(0, 100000)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            e = traceback.format_exc()
            e = "\n\nid:" + str(rdm) + "\n" + e
            with open('err.log', 'a') as f:
                f.write(e)
            print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET +
                  " " + exc_type.__name__ + ", id:" + str(rdm))
            return "Something really bad went wrong, and I don't know what it is yet." + \
                   " ^-^ Error:" + exc_type.__name__ + " id:" + str(rdm)

    def sendrec(self, message, name):
        recommend.recommend(self.osu_api_client)

class Bot(irc.IRCClient):
    """An IRC bot."""

    nickname = config.botnick
    password = config.password
    lineRate = 1
    heartbeatInterval = 64

    def __init__(self, first_time):
        self.first_time = first_time

    def logCommand(self, sentmsg, user):
        self.msg(user, sentmsg)
        self.logic.savetofile(sentmsg, open(
            os.path.join(os.path.relpath('log\\', os.path.dirname(__file__)), "sentcommands.txt"), "a"))

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.logic = ProgramLogic(open(self.factory.filename, "a"))
        self.logic.log("[connected at %s]" % time.asctime(time.localtime(time.time())))

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        self.logic.log("[disconnected at %s]" % time.asctime(time.localtime(time.time())))
        self.logic.close()

    # callbacks for events

    def signedOn(self):
        """Called when bot has successfully signed on to server."""
        print(colorama.Style.BRIGHT + "Signed in!")  # don't log

    def joined(self, channel):
        """Called when the bot joins the channel."""
        self.logic.log("[I have joined %s]" % channel)

    def privmsg(self, user, channel, msg):
        """Called when the bot receives a message."""
        global osu_library
        user = user.split('!', 1)[0]

        # Check to see if they're sending me a private message
        if channel == self.nickname:
            if msg.startswith(config.prefix):
                self.logic.check_update(self.logic.FIRST_TIME_MSG, user, "firsttime.txt")
                self.logic.check_update(self.logic.UPDATE_MSG, user, "updates.txt")
                command = msg.split(config.prefix, 1)[1].split()[0]

                # ~~~~~~~~~~~~~~~~~~~~~~~~ THE COMMANDS ~~~~~~~~~~~~~~~~~~~~~~~~
                if command == "set":
                    d = threads.deferToThread(self.logic.setpref, msg, user)
                    d.addCallback(self.logCommand, user)
                    d.addErrback(log.err)
                elif command == "acc":
                    d = threads.deferToThread(self.logic.sendpp, msg, user, "acm")
                    d.addCallback(self.logCommand, user)
                    d.addErrback(log.err)
                elif command == "with":
                    d = threads.deferToThread(self.logic.sendpp, msg, user, "mod")
                    d.addCallback(self.logCommand, user)
                    d.addErrback(log.err)
                # elif command == "keys":
                #     d = threads.deferToThread(self.logic.sendpp, msg, user, "key")
                #     d.addCallback(self.logCommand, user)
                #     d.addErrback(self.catchError, user)
                #     d.addErrback(log.err)
                elif command == "h":
                    self.msg(user, "Need help? Check [https://github.com/de-odex/FruityBot/wiki the wiki] for commands.")
                elif command == "r":
                    self.logic.sendrec(msg, user)
                    pass
                elif command == "uptime":
                    self.msg(user,
                             time.strftime("%H;%M;%S", time.gmtime(time.time() - self.first_time)) + " since start.")
                elif command == "time":
                    self.msg(user, "Local time: " + time.strftime("%B %d %H:%M:%S", time.localtime(time.time())))
                elif command == "botreport":
                    try:
                        attr = msg.split(" ", 1)[1]
                        self.msg(user, "Reported: " + attr)
                        self.logic.report(attr)
                    except:
                        self.msg(user, "What are you reporting?")
                else:
                    self.msg(user, "Invalid command. " + config.prefix + "h for help.")
                self.logic.log("<" + colorama.Fore.MAGENTA + user + colorama.Fore.WHITE + "> "
                               + colorama.Fore.YELLOW + msg)
            elif (user == self.nickname or user == config.adminname) and msg.startswith(config.adminprefix):
                command = msg.split(config.adminprefix, 1)[1].split()[0]
                if command == "exit":
                    self.msg(user, "Exiting...")
                    colorama.deinit()
                    reactor.stop()
                if command == "regen":
                    osu_library = slider.library.Library.create_db(libdir)
                    self.msg(user, "Regenerated osu! library.")
                if command == "reload":
                    try:
                        split_msg = msg.split()[1]
                        importlib.reload(importlib.import_module(split_msg))
                        self.msg(user, "Reloaded " + split_msg + ".")
                    except:
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        self.msg(user, "An error has occurred. " + exc_type.__name__)
                self.logic.log("<" + colorama.Fore.MAGENTA + user + colorama.Fore.WHITE + "> "
                               + colorama.Fore.BLUE + msg)
            else:
                self.logic.log("<" + colorama.Fore.MAGENTA + user + colorama.Fore.WHITE + "> "
                               + colorama.Fore.WHITE + msg)

    def action(self, user, channel, msg):
        """Called when the bot sees someone do an action."""
        user = user.split('!', 1)[0]
        self.logic.log(colorama.Fore.MAGENTA + "* " + user + colorama.Fore.WHITE + " " + msg)
        if channel == self.nickname:

            self.logic.check_update(self.logic.FIRST_TIME_MSG, user, "firsttime.txt")
            self.logic.check_update(self.logic.UPDATE_MSG, user, "updates.txt")
            d = threads.deferToThread(self.logic.sendpp, msg, user, "np")
            d.addCallback(self.logCommand, user)
            d.addErrback(log.err)

        else:
            pass


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    maxDelay = 5
    initialDelay = 5

    def __init__(self, filename):
        self.filename = filename
        self.first_time = time.time()

    def buildProtocol(self, addr):
        p = Bot(self.first_time)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET +
              ' Lost connection.  Reason:' + str(reason))
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print(colorama.Back.RED + colorama.Style.BRIGHT + " ERROR " + colorama.Back.RESET +
              ' Connection failed. Reason:' + str(reason))
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


def main():
    # initialize logging
    log.startLogging(sys.stdout)

    # create factory protocol and application
    f = BotFactory("logs.log")

    # connect factory to this host and port
    reactor.connectTCP(config.server, 6667, f)

    # run bot
    reactor.run()


if __name__ == '__main__':
    main()
