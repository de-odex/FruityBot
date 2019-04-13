import logging
import os
from pathlib import Path

import colorama
import cyclone.web
import i18n
import requests_respectful
from twisted.internet import protocol

if __name__ == "__main__" and __package__ is None:
    __package__ = "FruityBot.bot"

root_dir = Path(__file__).resolve().parent
os.chdir(root_dir)
colorama.init()
(root_dir / "log").mkdir(exist_ok=True)

from .logger import loginit

loginit(root_dir)
logger = logging.getLogger(__name__)

from .utils import convert_time, Config
from . import core_bot
from .localize import tl, load_locales
from . import database
from . import app


class FruityBot(core_bot.CoreBot):
    VERSION = 5

    def stop(self):
        self.user_pref.database.close()
        super().stop()

    def reload_init(self):
        self.root_dir = root_dir
        super().reload_init()

        user_pref_table = """CREATE TABLE IF NOT EXISTS user_pref(
                               username VARCHAR(64) PRIMARY KEY,
                               last_command DATETIME,
                               mode TINYINT,
                               locale TINYTEXT
                             )"""
        # FOREIGN KEY (username) REFERENCES user_ids(username)

        db_args = self.Config().mariadb
        database_file = database.DatabaseFile(db_args.user, db_args.password, db_args.database)

        self.user_pref = database.UserPrefTable(database_file, "user_pref", user_pref_table,
                                                ['1970-01-01 00:00:00', None, 'en'])
        self.user_pref.create()

        # migrate database.db
        if Path("./user_pref.csv").resolve().is_file():
            import csv
            import datetime
            with Path("./user_pref.csv").resolve().open('r') as csv_file:
                reader = csv.DictReader(csv_file, delimiter=',', quotechar='"')
                for line in reader:
                    line["last_command"] = datetime.datetime.strptime(line["last_command"], "%Y-%m-%dT%H:%M:%S.%f%z") \
                        .strftime("%Y-%m-%d %H:%M:%S")
                    self.user_pref[line.pop("username")] = {k: v for k, v in line.items()}
            Path("./user_pref.csv").unlink()

        self.users = {}
        load_locales()
        logger.debug("FruityBot.reload_init | bot initialized")

    def before_command(self, e, full_command):
        logger.debug("FruityBot.before_command | starting")

        # check if user in database
        if not e.source.nick in self.user_pref:
            logger.debug(f"FruityBot.before_command | user {e.source.nick} not in database")
            self.msg(e.source.nick, tl("general.first_time", self.user_pref.get(e.source.nick).locale))
            self.user_pref[e.source.nick] = {}

        if convert_time(self.user_pref[e.source.nick].last_command) < convert_time(self.Config().main.last_update):
            logger.debug(f"FruityBot.before_command | user {e.source.nick} outdated")
            self.msg(e.source.nick, tl("general.update", self.user_pref[e.source.nick].locale))
            self.user_pref.update_last_command(e.source.nick)

        logger.debug("FruityBot.before_command | finished")


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """
    delay = 5
    maxDelay = 5
    initialDelay = 5

    def __init__(self, channel=None):
        self.channel = channel
        self.instance = None

    def buildProtocol(self, addr):
        try:
            self.instance = None
            p = FruityBot(self.channel)
            p.factory = self
            self.instance = p
            return p
        except requests_respectful.exceptions.RequestsRespectfulRedisError:
            logger.exception("Redis Error")

    def clientConnectionLost(self, connector, reason):
        logger.warning('Lost connection.  Reason: ' + str(reason).replace('\n', '', 1).replace('\r', '', 1))
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logger.warning('Connection failed.  Reason:  ' + str(reason).replace('\n', '', 1).replace('\r', '', 1))
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


if __name__ == "__main__":
    if not Path(root_dir / "locale").is_dir():
        logger.critical("Locale folder missing; please create the locale folder with strings for translation support")
        exit()
    i18n.load_path.append(str(Path(root_dir / "locale")))
    logger.info("Logger initialized")
    logging.getLogger('twisted').setLevel(logging.INFO)

    from twisted.internet import reactor

    if Path("debug.json").is_file() and logger.getEffectiveLevel() == logging.DEBUG:
        _config = Config(root_dir / "debug.json")
    elif Path("config.json").is_file():
        _config = Config(root_dir / "config.json")
    elif Path("config.json.template").is_file():
        _config = Config(root_dir / "config.json.template")
    else:
        raise FileNotFoundError("No configuration file")

    # create factory protocol and application
    bot_factory = BotFactory(_config().main.channel if _config().main.channel else "")

    # connect factory to this host and port
    logger.info(f"Loading {_config.filename.name}")
    bot = reactor.connectTCP(_config().main.server, 6667, bot_factory)

    app_api = cyclone.web.Application([
        (r"/api/is_online", app.OnlineHandler, {"connector": bot}),
        (r"/api/info", app.InfoHandler, {"connector": bot})
    ])

    reactor.listenTCP(9559, app_api)

    reactor.run()
