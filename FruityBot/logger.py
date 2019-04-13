import json
import logging
import logging.config
from functools import partial, update_wrapper


class ColorFormatter(logging.Formatter):
    from colorama import Fore, Back, Style
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

    COLORS = {
        'WARNING':  (Style.DIM + Fore.BLACK, Back.YELLOW),
        'INFO':     (Style.BRIGHT + Fore.WHITE, Back.CYAN),
        'DEBUG':    (Style.NORMAL + Fore.WHITE, Back.BLUE),
        'CRITICAL': (Style.DIM + Fore.BLACK, Back.YELLOW),
        'ERROR':    (Style.BRIGHT + Fore.WHITE, Back.RED),
    }

    CCOLORS = {
        "BLACK":   BLACK,
        "RED":     RED,
        "GREEN":   GREEN,
        "YELLOW":  YELLOW,
        "BLUE":    BLUE,
        "MAGENTA": MAGENTA,
        "CYAN":    CYAN,
        "WHITE":   WHITE,
    }

    COLOR_SEQ = "\033[1;%dm"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record):
        level_name = record.levelname
        color = self.COLORS[level_name][0]
        bg_color = self.COLORS[level_name][1]
        message = logging.Formatter.format(self, record)
        message = message.replace("$RESET", self.Style.RESET_ALL) \
            .replace("$BRIGHT", self.Style.BRIGHT) \
            .replace("$COLOR", color) \
            .replace("$BGCOLOR", bg_color)
        for k, v in self.CCOLORS.items():
            message = message.replace("$" + k, self.COLOR_SEQ % (v + 30)) \
                .replace("$BG" + k, self.COLOR_SEQ % (v + 40))
        return message + self.Style.RESET_ALL


def loginit(root_dir):
    logging.ColorFormatter = ColorFormatter
    logging.config.dictConfig(json.load(open((root_dir / 'logging.json'), 'r')))


START_STR = "starting"
FINISH_STR = "finished"


def logger_deco_factory(logger):
    class decorator:
        def __init__(self, f):
            self._f = f
            update_wrapper(self, f)

        def __call__(self, instance, *args, **kwargs):
            f = self._f

            name_str = f"{type(instance).__name__}.{f.__name__}"

            args_kwargs_str = "; ".join((f"args = {args}" if args else "", f"kwargs = {kwargs}" if kwargs else ""))
            logger.debug(" | ".join(i for i in (name_str, START_STR, args_kwargs_str) if i is not ""))
            ret = f(instance, *args, **kwargs)
            ret_str = f"returned {ret}" if ret else ""
            logger.debug(" | ".join(i for i in (name_str, FINISH_STR, ret_str) if i is not ""))
            return ret

        def __get__(self, instance, owner):
            if instance is None:
                return self
            logger.debug(instance)
            return partial(self.__call__, instance)

    return decorator
