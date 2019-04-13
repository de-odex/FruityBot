import logging

import cyclone.web

from FruityBot.localize import LocaleException, get_locales, tl

logger = logging.getLogger(__name__)


class OnlineHandler(cyclone.web.RequestHandler):
    def initialize(self, connector):
        self.connector = connector
        self.bot = self.connector.factory.instance

    def get(self):
        if self.bot.connected == 0:
            self.send_error(503)  # service unavailable
        else:
            self.write(str(self.bot.connected))


class InfoHandler(cyclone.web.RequestHandler):
    def initialize(self, connector):
        self.connector = connector
        self.bot = self.connector.factory.instance

    def get(self):
        if self.request.remote_ip != '127.0.0.1':
            self.send_error(403)
            return
        locale = self.get_argument("locale", "en")

        help_dict = {k: {} for k in self.bot.command_func_names.keys() if not k == "Admin"}
        for module in help_dict:
            for command in self.bot.command_func_names[module]:
                func = getattr(self.bot.modules[f"{module.capitalize()}"][0], command)
                command = command if not command.startswith("cmd_") else command[4:]
                try:
                    help_dict[module][command] = tl(func.__dict__["cmd_help"], self.get_argument("locale", locale))
                except LocaleException as exc:
                    logger.exception("")
                    help_dict[module][command] = str(exc)

        self.write({'help': help_dict, 'locales': get_locales(), 'is_online': self.connector.state})
