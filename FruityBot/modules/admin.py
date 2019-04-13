import importlib
import logging

from ..core_bot.bot_module import Module, command, is_owner
from ..utils import reload_all

logger = logging.getLogger(__name__)


class Admin(Module):
    @is_owner
    @command
    def reload(self, e):
        logger.debug(self.bot.modules)
        self.bot.msg(e.source.nick, "Attempting a reload...")
        try:
            self.bot.msg(e.source.nick, f"Reloading {', '.join(list(self.bot.modules.keys()))}")
            for k, v in self.bot.modules.items():
                importlib.reload(v[1])
                self.bot.modules[k] = getattr(v[1], f"{k.capitalize()}")({}, self.bot), v[1]
            # logger.debug(self.modules)

            reload_all(__package__, 15)
            self.bot.reload_init()
            self.bot.msg(e.source.nick, "Reload successful!")
            logger.debug(self.bot.modules)
        except:
            logger.exception("Reload Exception")
            self.bot.msg(e.source.nick, "Reload failed! Terminating bot due to possible errors")
            self.bot.stop()

    @is_owner
    @command
    def disconnect(self, e):
        self.bot.msg(e.source.nick, "Reconnecting bot...")
        self.bot.quit()

    @is_owner
    @command(aliases=["kill", "stop", "end"])
    def die(self, e):
        self.bot.msg(e.source.nick, "Shutting down...")
        self.bot.stop()

    @is_owner
    @command
    def test(self, e):
        self.bot.msg(e.source.nick, f"{self.test.__name__}")

    @is_owner
    @command
    def version(self, e):
        self.bot.msg(e.source.nick, str(self.bot.VERSION))

    @is_owner
    @command
    def resetosu(self, e):
        self.bot.msg(e.source.nick, "Clearing self.users...")
        self.bot.users = {}
        self.bot.msg(e.source.nick, "self.users cleared")

    @is_owner
    @command
    def eval(self, e):
        self.bot.msg(e.source.nick, str(eval(' '.join(e.arguments[1:]))))

    @is_owner
    @command
    def whois(self, e):
        d = self.bot.get_whois()
        if d is not None:
            d.addCallback(lambda result: self.bot.msg(e.source.nick, result[2]))
        self.bot.whois(e.arguments[1])
