#!/usr/bin/env python
#
# Example program using irc.bot.
#
# Joel Rosdahl <joel@rosdahl.net>

"""A simple example bot.
This is an example bot that uses the SingleServerIRCBot class from
irc.bot.  The bot enters a channel and listens for commands in
private messages and channel traffic.  Commands in channel messages
are given by prefixing the text by the bot name followed by a colon.
It also responds to DCC CHAT invitations and echos data sent in such
sessions.
The known commands are:
    stats -- Prints some channel information.
    disconnect -- Disconnect the bot.  The bot will try to reconnect
                  after 60 seconds.
    die -- Let the bot cease to exist.
    dcc -- Let the bot invite you to a DCC CHAT connection.
"""

import irc.bot
import irc.strings
from irc.client import ip_numstr_to_quad, ip_quad_to_numstr
import logging
import logging.config

#mine
import os
import importlib

import sqlite3
import utils
import pathlib
import slider

logging.config.fileConfig('logging.conf')
logger = logging.getLogger()


class FruityBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, port=6667, test=False):
        self.test = test

        try:
            self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.userdb = sqlite3.connect('userpref.db')
        self.upcur = self.userdb.cursor()
        try:
            self.upcur.execute("CREATE TABLE IF NOT EXISTS userdb (user INT PRIMARY KEY, mode INT, info INT)")
        except self.userdb.Error:
            logger.error("Failed to create the user database!")

        # test for info column
        self.results = self.upcur.execute("PRAGMA table_info(userdb)").fetchall()
        self.results2 = []
        for i in self.results:
            self.results2.append(i[1])
        if "info" not in self.results2:
            self.upcur.execute("ALTER TABLE userdb ADD info INT")

        irc.bot.SingleServerIRCBot.__init__(self, [(self.Config.config.main.server, port)],
                                            self.Config.config.main.nick, self.Config.config.main.nick)
        self.channel = channel

        self.UPDATE_MSG = self.Config.config.main.update_msg
        self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg

        self.users = {}
        self.libdir = pathlib.Path("./osulib").absolute()

        if not self.libdir.exists():
            os.makedirs(self.libdir)
            self.osu_library = slider.library.Library.create_db(self.libdir)
            logger.info("Created osu! library")
        else:
            self.osu_library = slider.library.Library(self.libdir)
        self.osu_api_client = slider.client.Client(self.osu_library, self.Config.config.osu.api)

        self.Commands = utils.Commands(self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]

    def on_welcome(self, c, e):
        logger.info("Bot started")
        c.join(self.channel)
        if self.test:
            self.die()

    def on_privmsg(self, c, e):
        logger.info(e.source.nick + ": " + e.arguments[0])
        self.do_command(e, e.arguments[0])

    def on_action(self, c, e):
        logger.info("* " + e.source.nick + " " + e.arguments[0])
        self.Commands.np(self, c, e)

    # def on_pubmsg(self, c, e):
    #     a = e.arguments[0].split(":", 1)
    #     if len(a) > 1 and irc.strings.lower(a[0]) == irc.strings.lower(self.connection.get_nickname()):
    #         # if () and first part of e.args[0] is the bot's nick
    #         self.do_command(e, a[1].strip())
    #     return

    def do_command(self, e, cmd):
        c = self.connection

        # check if user in database
        in_db = utils.Utils.check_user_in_db(e.source.nick, 'userpref.db', "ftm")
        if not in_db:
            c.notice(e.source.nick, self.FIRST_TIME_MSG)
        in_db = utils.Utils.check_user_in_db(e.source.nick, 'userpref.db', "um")
        if not in_db:
            c.notice(e.source.nick, self.UPDATE_MSG)

        if cmd == self.Config.config.main.prefix + "reload":
            if e.source.nick == self.Config.config.main.owner:
                c.notice(e.source.nick, "Attempting a reload...")
                try:
                    importlib.reload(utils)
                    self.Config = utils.Config("config.json")
                    self.Commands = utils.Commands(self.Config)
                    self.UPDATE_MSG = self.Config.config.main.update_msg
                    self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg
                    self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                                          and not func.startswith("_")]
                    self.osu_library = slider.library.Library.create_db(self.libdir)
                    self.osu_api_client = slider.client.Client(self.osu_library, self.Config.config.osu.api)
                    c.notice(e.source.nick, "Reload successful!")
                except:
                    logger.exception("Reload Exception")
                    c.notice(e.source.nick, "Reload failed! Killing bot due to possible errors.")
                    self.die()
            else:
                c.notice(e.source.nick, "You do not have the permissions to run this command!")
        else:
            command_incurred = False
            for i in self.command_funcs:
                if cmd.split()[0] == self.Config.config.main.prefix+i or cmd.split()[0] == self.Config.config.main.prefix+i[4:] and i[:4] == "cmd_":
                    command_incurred = True
                    func = getattr(utils.Commands, i)
                    func(self.Commands, self, c, e)
            if not command_incurred:
                c.notice(e.source.nick, "Not understood: " + cmd)


def main():
    channel = "#bottest"

    bot = FruityBot(channel)
    bot.start()


if __name__ == "__main__":
    main()
