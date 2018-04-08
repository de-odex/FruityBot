import datetime
import logging.config
import os
import pathlib

from irc.client import NickMask, Event
from twisted.internet import reactor, protocol, threads
from twisted.words.protocols import irc

import utils

logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)


class FruityBot(irc.IRCClient):
    def rawDataReceived(self, data):
        raise NotImplementedError

    def dccSend(self, user, file):
        raise NotImplementedError

    lineRate = 1
    heartbeatInterval = 64

    def reload_init(self, first_time, users):
        try:
            try:
                self.Config = utils.Config("debug.json")
            except FileNotFoundError:
                self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.nickname = self.Config.config.main.nick
        self.password = self.Config.config.osu.irc if self.Config.config.osu.irc else None

        self.UPDATE_MSG = self.Config.config.main.update_msg
        self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg

        self.user_pref = utils.Utils.create_sqlite_dict("./userpref.db", "userpref")
        self.recommend = utils.Utils.create_sqlite_dict("./recommend.db", "recommend")
        self.start_time = first_time

        self.users = users

        self.Commands = utils.Commands(self, self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]

    def __init__(self, first_time, users, channel=None, test=False):
        self.test = test
        self.channel = channel

        # region reload_init
        try:
            try:
                self.Config = utils.Config("debug.json")
            except FileNotFoundError:
                self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.nickname = self.Config.config.main.nick
        self.password = self.Config.config.osu.irc if self.Config.config.osu.irc else None

        self.UPDATE_MSG = self.Config.config.main.update_msg
        self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg

        self.user_pref = utils.Utils.create_sqlite_dict("./userpref.db", "userpref")
        self.recommend = utils.Utils.create_sqlite_dict("./recommend.db", "recommend")
        self.start_time = first_time

        self.users = users

        self.Commands = utils.Commands(self, self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]
        # endregion

        logger.debug("Trying nickname " + self.nickname)
        logger.debug("On server " + self.Config.config.main.server)
        logger.debug("Using password " + (self.password if self.password is not None else "\"None\""))

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        logger.warning("Nick error! Someone of " + self.nickname + " nickname already exists")
        self.nickname = self.nickname + "_"
        self.setNick(self.nickname)
        logger.info("Now using " + self.nickname)

    def signedOn(self):
        logger.info("Bot started as " + self.nickname + " at " + self.Config.config.main.server)
        self.startHeartbeat()
        if self.channel is not None and self.Config.config.main.server != "cho.ppy.sh" or \
           self.Config.config.main.server != "irc.ppy.sh":
            self.join(self.channel)
        if self.test:
            self.quit()

    def joined(self, channel):
        logger.info("I have joined " + channel)

    def privmsg(self, user_host, channel, msg):
        user = user_host.split('!', 1)[0]
        logger.info(user + ": " + msg)
        if msg[0] == self.Config.config.main.prefix:
            try:
                threads.deferToThread(self.message_to_commands, user_host, channel, msg)
            except Exception:
                logger.exception("Deferred Exception")
                self.msg(user, "Falling back to single-thread...")
                self.message_to_commands(user_host, channel, msg)

    def action(self, user_host, channel, data):
        user = user_host.split('!', 1)[0]
        logger.info("* " + user + " " + data)
        try:
            threads.deferToThread(self.message_to_commands, user_host, channel, "!np " + data)
        except Exception:
            logger.exception("Deferred Exception")
            self.msg(user, "Falling back to single-thread...")
            self.message_to_commands(user_host, channel, "!np " + data)

    def message_to_commands(self, user_host, target, msg):
        commands = msg.split(self.Config.config.main.prefix)[1].split(";")
        for msgs in commands:
            msgs = msgs.strip()
            self.do_command(user_host, target, msgs)

    def do_command(self, user_host, target, msg):
        cmd = msg.split()[0]
        e = Event("", NickMask(user_host), target, [msg])

        if cmd == "reload":
            logger.debug("Command incurred: " + cmd)
            if e.source.nick == self.Config.config.main.owner:
                self.msg(e.source.nick, "Attempting a reload...")
                try:
                    utils.reload_all(utils, 3)
                    self.reload_init(self.start_time, self.users)
                    self.msg(e.source.nick, "Reload successful!")
                except:
                    logger.exception("Reload Exception")
                    self.msg(e.source.nick, "Reload failed! Killing bot due to possible errors.")
                    self.quit()
                    reactor.callFromThread(reactor.stop)
        else:
            if cmd.split()[0] in self.command_funcs or \
                    any((cmd.split()[0] in s and s[:4] == "cmd_") for s in self.command_funcs):
                logger.debug("Command incurred: " + cmd)
                # check if user in database
                in_f_db = utils.Utils.check_user_in_db(e.source, self, "ftm")
                if not in_f_db:
                    self.msg(e.source.nick, self.FIRST_TIME_MSG)
                in_u_db = utils.Utils.check_user_in_db(e.source, self, "um")
                if not in_u_db:
                    self.msg(e.source.nick, self.UPDATE_MSG)

                i = cmd.split()[0]
                if any((cmd.split()[0] in s and s[:4] == "cmd_") for s in self.command_funcs):
                    i = "cmd_" + i

                func = getattr(utils.Commands, i)
                func(self.Commands, self, e)
            else:
                self.msg(e.source.nick, "Invalid command: " + cmd + ". " +
                         self.Config.config.main.prefix + "h for help.")


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    maxDelay = 5
    initialDelay = 5

    def __init__(self, channel=None):
        self.first_time = datetime.datetime.now()
        self.channel = channel
        self.users = {}

    def buildProtocol(self, addr):
        p = FruityBot(self.first_time, self.users, self.channel)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        logger.warning('Lost connection.  Reason:' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logger.warning('Connection failed.  Reason:' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


def main():
    if not pathlib.Path("./log/").exists():
        os.mkdir("./log/")

    logger.debug("Start of __main__")

    # create factory protocol and application
    f = BotFactory("bottest")

    # connect factory to this host and port
    try:
        try:
            reactor.connectTCP(utils.Config("debug.json").config.main.server, 6667, f)
        except FileNotFoundError:
            reactor.connectTCP(utils.Config("config.json").config.main.server, 6667, f)
    except FileNotFoundError:
        reactor.connectTCP(utils.Config("config.json.template").config.main.server, 6667, f)

    # run bot
    reactor.run()


if __name__ == "__main__":
    main()
