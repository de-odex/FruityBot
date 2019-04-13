import pytest
from irc.client import Event, NickMask

from . import osu
from ..utils import Config
from io import StringIO
import sys

import re


class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio  # free up some memory
        sys.stdout = self._stdout


class DummyBot():
    def __init__(self):
        self.users = {}
        self.user_pref = {}
        self.locale = {}
        self.Config = Config("FruityBot/debug.json")

    def msg(self, dest, msg):
        print(f"MSG: bot -> {dest}: {msg}")


@pytest.fixture(scope='module')
def stuff():
    bot = DummyBot()
    return (bot,
            Event("", NickMask("aEverr!~aEverr@192.168.0.1"), "FruityBot", []),
            osu.Osu({}, bot))


@pytest.mark.parametrize("link, expected", [
    ("https://osu.ppy.sh/beatmapsets/457332#fruits/1514618", ['1002.26pp', '975.01pp', '948.36pp', '922.32pp']),
    ("https://osu.ppy.sh/beatmapsets/400761#taiko/871924", ['453.35pp', '433.07pp', '415.17pp']),

])
def test_np(stuff, link, expected):
    bot, e, osu_class = stuff
    e.arguments = [f"!np {link}"]
    with Capturing() as output:
        osu_class.np(bot, e)
    print(output)
    assert re.findall(r"\d+?.?\d+?pp", output[-1]) == expected


@pytest.mark.parametrize("link, args, expected", [
    ("https://osu.ppy.sh/beatmapsets/457332#fruits/1514618", "99.9381443298969 3927x 0m", ['998.86pp']),
    ("https://osu.ppy.sh/beatmapsets/400761#taiko/871924", "92.94755877034359 624x 4m", ['332.77pp']),
    ("https://osu.ppy.sh/beatmapsets/436217#mania/939698", "99.87623762376238 996483s", ['214.01pp']),
    # https://osu.ppy.sh/api/get_scores?k=lol&b=939698&u=7014697&m=3
])
def test_acc(stuff, link, args, expected):
    bot, e, osu_class = stuff
    e.arguments = [f"!np {link}"]
    osu_class.np(bot, e)
    e.arguments = [f"!acc {args}"]  # from https://osu.ppy.sh/users/8403032/fruits
    with Capturing() as output:
        osu_class.acc(bot, e)
    print(output)
    assert re.findall(r"\d+?.?\d+?pp", output[-1]) == expected


@pytest.mark.parametrize("link, args, mods, expected", [
    ("https://osu.ppy.sh/beatmapsets/457332#fruits/1514618", "99.85567010309279 3880x 4m", "hd", ['935.04pp']),


])
def test_mod(stuff, link, args, mods, expected):
    bot, e, osu_class = stuff
    e.arguments = [f"!np {link}"]
    osu_class.np(bot, e)
    e.arguments = [f"!acc {args}"]  # from https://osu.ppy.sh/users/3657951/fruits
    osu_class.acc(bot, e)
    e.arguments = [f"!with {mods}"]
    with Capturing() as output:
        osu_class.cmd_with(bot, e)
    print(output)
    assert re.findall(r"\d+?.?\d+?pp", output[-1]) == expected

