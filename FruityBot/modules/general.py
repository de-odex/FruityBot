import logging

import slider
from ..core_bot.bot_module import Module, command
from ..localize import LocaleException, alpha_2_langs, get_locales, tl
from ..utils import set_pref

logger = logging.getLogger(__name__)


class General(Module):
    class UnknownSetException(Exception):
        pass

    class UnknownSetArgsException(Exception):
        pass

    def __init__(self, state, bot):
        super().__init__(state, bot)
        self.usables = {
            'acc':  ("", "!acc (acc) (miss)m", "!acc (acc) (combo)x (miss)m", "!acc (score)s"),
            'with': ("", "nf, ez, hd, hr, fl", "dt, hd, fl", "nf, ez")
        }

    @command(aliases=["h"])
    def help(self, e):
        args = ' '.join(e.arguments).split(maxsplit=2)
        if len(args) > 1:
            if args[1] == "acc" or args[1] == "with":
                find = args[1] + "_mode"
            else:
                find = args[1]

            # TODO: make a show all commands subcommand

            try:
                self.bot.msg(e.source.nick, f"{self.bot.Config().main.prefix}{args[1]}: " +
                             tl(f"help.{find}", self.bot.user_pref[e.source.nick].locale)
                             .format(
                                 v=self.usables.get(
                                     args[1], ("", "", "", "")
                                 )[self.bot.user_pref[e.source.nick].mode])
                             )
                # formats if tl returns string with {v} in it, signifies a command that changes per game mode
            except LocaleException:
                self.bot.msg(e.source.nick, tl("general.help", self.bot.user_pref[e.source.nick].locale))
        else:
            self.bot.msg(e.source.nick, tl("general.help", self.bot.user_pref[e.source.nick].locale))

    @command
    def set(self, e):
        try:
            e.arguments[1]
        except IndexError:
            return self.bot.msg(e.source.nick, tl("set.setting_invalid", self.bot.user_pref[e.source.nick].locale))

        try:
            try:
                getattr(self, f"set_{e.arguments[1].lower()}")(e, e.arguments)
            except AttributeError:
                raise self.UnknownSetException
            self.bot.msg(e.source.nick,
                         tl("set.setting", self.bot.user_pref[e.source.nick].locale).format(e.arguments[1],
                                                                                            e.arguments[2]))
        except (self.UnknownSetArgsException, IndexError) as exc:
            if type(exc) is self.UnknownSetArgsException:
                self.bot.msg(e.source.nick, tl(f"set.{e.arguments[1]}_invalid",
                                               self.bot.user_pref[e.source.nick].locale))
            return self.bot.msg(e.source.nick, tl(f"set.how_to_{e.arguments[1]}",
                                                  self.bot.user_pref[e.source.nick].locale))
        except self.UnknownSetException:
            self.bot.msg(e.source.nick, tl("set.setting_invalid", self.bot.user_pref[e.source.nick].locale))

    def set_mode(self, e, args):
        try:
            mode = slider.GameMode.parse(args[2].lower())
        except:
            raise self.UnknownSetArgsException
        if mode == slider.GameMode.standard:
            self.bot.msg(e.source.nick, tl("set.tillerino", self.bot.user_pref[e.source.nick].locale))
            return False
        set_pref(e.source, self.bot, 'mode', int(mode))
        return True

    def set_lang(self, e, args):
        if args[2].lower() in alpha_2_langs and args[2].lower() in get_locales():
            set_pref(e.source, self.bot, 'locale', args[2])
            return True
        else:
            raise self.UnknownSetArgsException
