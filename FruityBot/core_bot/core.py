import importlib
import logging
import pathlib

import redis
from irc.client import Event, NickMask
from twisted.internet import defer, reactor, threads
from twisted.python import threadpool
from twisted.words.protocols import irc

from ..utils import Config, ThreadDict

logger = logging.getLogger(__name__)


class CoreBot(irc.IRCClient):
    def rawDataReceived(self, data):
        raise NotImplementedError

    def dccSend(self, user, file):
        raise NotImplementedError

    lineRate = 1
    heartbeatInterval = 64

    VERSION = 1

    def stop(self):
        self.quit()
        reactor.callFromThread(reactor.callLater, 5, reactor.callFromThread, reactor.stop)
        for v in self.thread_pools.values():
            reactor.callFromThread(v.stop)

    def reload_init(self):
        try:
            getattr(self, 'root_dir')
        except AttributeError:
            self.root_dir = pathlib.Path(__file__).resolve().parent

        logger.info(f"Running version {self.VERSION} of core bot")

        if pathlib.Path(self.root_dir / "debug.json").is_file() and logger.getEffectiveLevel() == logging.DEBUG:
            self.Config = Config(self.root_dir / "debug.json")
        elif pathlib.Path(self.root_dir / "config.json").is_file():
            self.Config = Config(self.root_dir / "config.json")
        elif pathlib.Path(self.root_dir / "config.json.template").is_file():
            self.Config = Config(self.root_dir / "config.json.template")
        else:
            raise FileNotFoundError("No configuration file")

        self.nickname = self.Config().main.nick
        self.password = self.Config().main.password if self.Config().main.password else None

        self.thread_pools = ThreadDict(10)

        self.cache_redis = redis.Redis(port=6379, db=0)

        self.modules = {}

        for module in self.Config().main.modules:
            logger.info(f"Loading module \"{module}\"")
            imodule = importlib.import_module(f"..modules.{module}", package=__package__)
            self.modules[f"{str(module).capitalize()}"] = (getattr(imodule, f"{str(module).capitalize()}")({}, self),
                                                           imodule)
            logger.info(f"Module \"{module}\" loaded successfully")

        function_tuples = tuple((k, v[0].get_functions()) for k, v in self.modules.items())
        self.command_func_names = {k: v[0] for k, v in function_tuples}
        self.command_funcs = {k: v[1] for k, v in function_tuples}
        self.alias_to_func = {}
        for module_funcs in self.command_funcs.values():
            for func in module_funcs:
                for key in func.__dict__["cmd_aliases"]:
                    self.alias_to_func[key] = func
        logger.debug(f"CoreBot.reload_init | aliases: {self.alias_to_func}")

        logger.debug(f"CoreBot.reload_init | functions loaded: {self.command_func_names}")

        self.whois_result = None

    def __init__(self, channel=None):
        self.channel = channel

        self.reload_init()

        logger.info(f"Trying nickname {self.nickname} on server {self.Config().main.server}"
                    f"{' using password ' + self.password if self.password is not None else ''}")

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        logger.warning(f"Someone of nickname {self.nickname} already exists")
        self.nickname = self.nickname + "_"
        self.setNick(self.nickname)
        logger.info(f"Now using {self.nickname}")

    def signedOn(self):
        logger.info(f"Bot signed on as {self.nickname} at {self.Config().main.server}"
                    f"{' with password ' + self.password if self.password else ''}")
        if self.channel is not None:
            self.join(self.channel)

    def joined(self, channel):
        self.msg(self.Config().main.owner, "Bot started.")
        logger.info(f"JOIN: BOT:{channel}")

    def privmsg(self, user_host, channel, msg):
        # check if private message
        if channel != self.nickname:
            return

        # create pseudo-event object
        e = Event("privmsg", NickMask(user_host), channel, msg.split())
        logger.info(f"MESSAGE: BOT:{self.nickname} <- USER:{e.source.nick}: {msg}")
        self.on_msg(e)

    def action(self, user_host, channel, msg):
        # check if private message
        if channel != self.nickname:
            return

        # create pseudo-event object
        e = Event("action", NickMask(user_host), channel, ("!action " + msg).split())
        logger.info(f"ACTION: BOT:{self.nickname} <- USER:{e.source.nick} {msg}")
        self.on_msg(e)

    def on_msg(self, e):
        # check if message is a command
        if ' '.join(e.arguments)[len(self.Config().main.prefix) - 1] == self.Config().main.prefix \
                and len(' '.join(e.arguments)) > 1:
            try:
                # check if user has a threadpool
                if e.source.nick in self.thread_pools:
                    user_pool = self.thread_pools[e.source.nick]
                else:
                    user_pool = threadpool.ThreadPool(1, 1, e.source.nick)
                    self.thread_pools[e.source.nick] = user_pool
                threads.deferToThreadPool(reactor, user_pool, self.message_to_commands, e)
                user_pool.start()
            except Exception:
                logger.exception("Deferred Exception")
                # revert to single thread method
                self.message_to_commands(e)

    def message_to_commands(self, e):
        # if command is a compound multiple command (has semicolons) execute in order
        for command in ' '.join(e.arguments).split(self.Config().main.prefix)[1].split(";"):
            # for command in a list of full string minus prefix split by semicolons

            self.do_command(e, command.strip())

    def do_command(self, e, full_command):
        command = full_command.split()[0]
        # command word is first word

        try:
            if self.alias_to_func.get(command, None):
                self.run_module_command(e, full_command)
            else:
                self.msg(e.source.nick, f"Invalid command: {command}. {self.Config().main.prefix}h for help.")
        except Exception as exc:
            logger.exception("")
            self.msg(e.source.nick, f"An unhandled exception has occurred: {type(exc).__qualname__}, {exc}")

    def run_module_command(self, e, full_command):
        command = full_command.split()[0]
        func = self.alias_to_func.get(command, None)
        if not func:
            raise ModuleNotFoundError()
        module = type(func.__self__)

        logger.debug(f"CoreBot.run_module_command | command incurred: {command}; function {func.__name__} "
                     f"in module {module.__qualname__!s}")

        self.before_command(e, full_command)
        ret = func(e)
        if ret and isinstance(ret, str):
            logger.debug(f"CoreBot.run_module_command | sending returned string: {ret}")
            self.msg(e.source.nick, ret)
        self.after_command(e, full_command)

    def before_command(self, e, full_command):
        pass

    def after_command(self, e, full_command):
        pass

    def msg(self, user, message, length=None):
        logger.info(f"MESSAGE: BOT:{self.nickname} -> USER:{user}: {message}")
        super().msg(user, message, length)

    def get_whois(self):
        self.whois_result = defer.Deferred()
        return self.whois_result

    def irc_RPL_WHOISUSER(self, prefix, params):
        if self.whois_result is not None:
            self.whois_result.callback(params)
