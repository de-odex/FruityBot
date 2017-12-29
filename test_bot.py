import bot
import pytest


def test_connection():
    testbot = bot.FruityBot("#bottest", test=True)
    with pytest.raises(SystemExit):
        testbot.start()
