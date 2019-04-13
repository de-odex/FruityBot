import logging
from datetime import datetime

from box import Box

from FruityBot import database
from pathlib import Path
import pytest

multiply = lambda x, y: x * y


def setup_module(module):
    print(f"setup_module      module:{module.__name__}")


def teardown_module(module):
    print(f"teardown_module   module:{module.__name__}")


def setup_function(function):
    print(f"setup_function    function:{function.__name__}")


def teardown_function(function):
    print(f"teardown_function function:{function.__name__}")


@pytest.fixture(scope='module', autouse=True)
def logger_obj(request):
    print(f"setup_resource    resource:logger")
    logging.basicConfig(level=logging.DEBUG)

    def logger_teardown():
        print(f"teardown_resource resource:logger")

    request.addfinalizer(logger_teardown)


@pytest.fixture(scope='module')
def database_obj(request):
    print(f"setup_resource    resource:database")

    user_pref_table = """CREATE TABLE IF NOT EXISTS user_prefs(
                                   username VARCHAR(255) PRIMARY KEY,
                                   last_command DATETIME,
                                   mode TINYINT,
                                   locale TINYTEXT
                                 )"""
    database_file = database.DatabaseFile('root', 'asterism', 'fruitybot_test')
    user_pref = database.UserPrefTable(database_file, "user_prefs", user_pref_table,
                                       ['1970-01-01 00:00:00', None, 'en'])
    user_pref.create()

    def database_teardown():
        print(f"teardown_resource resource:database")

    request.addfinalizer(database_teardown)

    return user_pref


def test_database_full_set(database_obj):
    database_obj["de/odex"] = {"mode": 3, "locale": "en"}
    logging.debug(database_obj["de/odex"])
    assert Box({'username': 'de/odex', 'last_command': datetime(1970, 1, 1, 0, 0), 'mode': 3, 'locale': 'en'}) \
           == database_obj["de/odex"]


def test_database_modify_set(database_obj):
    database_obj["de/odex"] = {"mode": 2, "locale": "ja"}
    logging.debug(database_obj["de/odex"])
    assert Box({'username': 'de/odex', 'last_command': datetime(1970, 1, 1, 0, 0), 'mode': 2, 'locale': 'ja'}) \
           == database_obj["de/odex"]

def test_database_contains_true(database_obj):
    assert ("de/odex" in database_obj) == True

def test_database_delete(database_obj):
    del database_obj["de/odex"]
    with pytest.raises(IndexError):
        database_obj["de/odex"]

def test_database_contains_false(database_obj):
    assert ("de/odex" in database_obj) == False