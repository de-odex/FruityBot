import bot
import datetime
import pytest


def test_connection():
    testbot = bot.FruityBot(datetime.datetime.now(), {}, channel=None, test=False)
    with pytest.raises(SystemExit):
        testbot.start()
