import datetime
import logging.config
import os
import pathlib

import colorama
import cyclone.web
from irc.client import Event, NickMask
from twisted.internet import protocol, reactor, threads
from twisted.python import threadpool
from twisted.words.protocols import irc

import utils


class FruityBot(irc.IRCClient):
    def rawDataReceived(self, data):
        raise NotImplementedError

    def dccSend(self, user, file):
        raise NotImplementedError

    lineRate = 1
    heartbeatInterval = 64

    def reload_init(self, first_time: datetime.datetime, users: dict):
        try:
            try:
                self.Config = utils.Config("debug.json")
            except FileNotFoundError:
                self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.nickname = self.Config().main.nick
        self.password = self.Config().osu.irc if self.Config().osu.irc else None

        self.UPDATE_MSG = self.Config().main.update_msg
        self.FIRST_TIME_MSG = self.Config().main.first_time_msg

        self.user_pref = utils.Utils.create_sqlite_dict("./userpref.db", "userpref")
        self.recommend = utils.Utils.create_sqlite_dict("./recommend.db", "recommend")
        self.start_time = first_time

        self.users = users
        self.thread_pools = utils.RecentDict(30)

        self.Commands = utils.Commands(self, self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]

    def __init__(self, first_time, users, channel=None):
        self.channel = channel

        # region reload_init
        try:
            try:
                self.Config = utils.Config("debug.json")
            except FileNotFoundError:
                self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.nickname = self.Config().main.nick
        self.password = self.Config().osu.irc if self.Config().osu.irc else None

        self.UPDATE_MSG = self.Config().main.update_msg
        self.FIRST_TIME_MSG = self.Config().main.first_time_msg

        self.user_pref = utils.Utils.create_sqlite_dict("./userpref.db", "userpref")
        self.recommend = utils.Utils.create_sqlite_dict("./recommend.db", "recommend")
        self.start_time = first_time

        self.users = users
        self.thread_pools = utils.RecentDict(30)

        self.Commands = utils.Commands(self, self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]
        # endregion

        logger.debug("Trying nickname " + self.nickname)
        logger.debug("On server " + self.Config().main.server)
        logger.debug("Using password " + (self.password if self.password is not None else "\"None\""))

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        logger.warning("Nick error! Someone of " + self.nickname + " nickname already exists")
        self.nickname = self.nickname + "_"
        self.setNick(self.nickname)
        logger.info("Now using " + self.nickname)

    def signedOn(self):
        logger.info("Bot started as " + self.nickname + " at " + self.Config().main.server)
        self.startHeartbeat()
        if self.channel is not None and self.Config().main.server != "cho.ppy.sh" or \
                self.Config().main.server != "irc.ppy.sh":
            self.join(self.channel)

    def joined(self, channel):
        logger.info("Joined " + channel)

    def privmsg(self, user_host, channel, msg):
        user = user_host.split('!', 1)[0]
        logger.info(f"MSG: BOT:{self.nickname} <- USER: {user}: {msg}")
        self.on_msg(user_host, channel, msg)

    def action(self, user_host, channel, msg):
        user = user_host.split('!', 1)[0]
        logger.info(f"ACT: BOT:{self.nickname} <- USER: *{user} {msg}")
        self.on_msg(user_host, channel, "!np " + msg)

    def on_msg(self, user_host, channel, msg):
        user = user_host.split('!', 1)[0]
        if msg[0] == self.Config().main.prefix:
            try:
                if user in self.thread_pools:
                    user_pool = self.thread_pools[user]
                else:
                    user_pool = threadpool.ThreadPool(5, 10, user)
                    self.thread_pools[user] = user_pool
                threads.deferToThreadPool(reactor, user_pool, self.message_to_commands, user_host, channel, msg)
                user_pool.start()
            except Exception:
                logger.exception("Deferred Exception")
                self.msg(user, "Falling back to single-thread...")
                self.message_to_commands(user_host, channel, msg)

    def message_to_commands(self, user_host, target, command):
        commands = command.split(self.Config().main.prefix)[1].split(";")
        for command in commands:
            command = command.strip()
            self.do_command(user_host, target, command)

    def do_command(self, user_host, target, msg):
        cmd = msg.split()[0]
        e = Event("", NickMask(user_host), target, [msg])

        if cmd == "reload":
            logger.debug("Command incurred: " + cmd)
            if e.source.nick == self.Config().main.owner:
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
                         self.Config().main.prefix + "h for help.")

    def msg(self, user, message, length=None):
        logger.info(f"MSG: BOT:{self.nickname} -> USER:{user}: {message}")
        super().msg(user, message, length)


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    delay = 5
    maxDelay = 5
    initialDelay = 5
    jitter = 0
    factor = 0

    def __init__(self, channel=None):
        self.first_time = datetime.datetime.now()
        self.channel = channel
        self.users = {}

    def buildProtocol(self, addr):
        p = FruityBot(self.first_time, self.users, self.channel)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        logger.warning('Lost connection.  Reason: ' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logger.warning('Connection failed.  Reason:  ' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


class OnlineHandler(cyclone.web.RequestHandler):
    def initialize(self, connector):
        self.connector = connector

    def get(self):
        if self.connector.state != "connected":
            self.set_status(404)
        else:
            self.write(self.connector.state)


if __name__ == "__main__":
    colorama.init()
    logging.ColorFormatter = utils.ColorFormatter
    logging.config.fileConfig('logging.conf')
    logger = logging.getLogger(__name__)

    if not pathlib.Path("./log/").exists():
        os.mkdir("./log/")

    # create factory protocol and application
    f_bot = BotFactory("bottest")

    # connect factory to this host and port
    try:
        try:
            bot = reactor.connectTCP(utils.Config("debug.json").config.main.server, 6667, f_bot)
        except FileNotFoundError:
            bot = reactor.connectTCP(utils.Config("config.json").config.main.server, 6667, f_bot)
    except FileNotFoundError:
        bot = reactor.connectTCP(utils.Config("config.json.template").config.main.server, 6667, f_bot)

    a_api = cyclone.web.Application([
        (r"/api/is_online", OnlineHandler, {"connector": bot})
    ])

    reactor.listenTCP(9009, a_api)

    print()
    # run bot
    reactor.run()
