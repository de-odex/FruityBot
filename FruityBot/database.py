import datetime
import functools
import logging
from threading import Lock

import MySQLdb as mariadb
import box

logger = logging.getLogger(__name__)


class DatabaseFile:
    def __init__(self, user, password, database):
        self.db_args = (user, password, database)
        self.database_name = database
        self.execute_mutex = Lock()
        self._conn = mariadb.connect(user=user, password=password)
        self.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        self.close()
        self.connect(user, password, database)

    def connect(self, user, password, database):
        try:
            self._conn = mariadb.connect(user=user, password=password, database=database)
            logger.debug("DatabaseFile.connect | connection made")
            return True
        except mariadb.Error:
            logger.exception("")
        return False

    def close(self):
        self._conn.close()

    @property
    def conn(self):
        return self._conn

    def execute(self, cmd, args=None):
        with self.execute_mutex as __:
            if type(cmd) == str:
                try:
                    cursor = self.conn.cursor()
                    cursor.execute(cmd, args)
                except (AttributeError, mariadb.OperationalError) as exc:
                    if eval(str(exc))[0] in [2013, 2006]:
                        logger.debug("DatabaseFile.execute | reconnecting to db")
                        self.connect(*self.db_args)
                        cursor = self.conn.cursor()
                        cursor.execute(cmd, args)
                    else:
                        raise
            else:
                raise TypeError
            ret = cursor.fetchall()
            cursor.close()
            self.conn.commit()
            return ret


class DatabaseTable:
    def __init__(self, database, table_name, create_query, defaults):
        if type(database) != DatabaseFile:
            raise TypeError
        self.database = database

        self.table_name = table_name
        self.create_query = create_query  # query to create the table
        self.defaults = defaults  # defaults of each column on the table

        self.write_mutex = Lock()

    def create(self):
        self._execute(self.create_query)

    def execute(self, cmd, args=tuple()):
        logger.debug(f"DatabaseTable.execute | {' '.join(cmd.split())} with args {args}")
        self._primary_keys.cache_clear()
        self._columns.cache_clear()
        self._table_info.cache_clear()
        return self._execute(cmd, args)

    def _execute(self, cmd, args=tuple()):
        args = tuple(map(str, args))
        return self.database.execute(cmd, args)

    def has_key(self, key):
        return self.__contains__(key)

    @functools.lru_cache()
    def __getitem__(self, key):
        cursor = self._execute(f"SELECT * FROM {self.table_name} WHERE {self._primary_keys()[0]}=%s", (key,))
        try:
            obj = [box.Box(dict(zip(self._columns(), i))) for i in cursor][0]
        except IndexError as exc:
            raise KeyError from exc
        if obj:
            logger.debug(f"DatabaseTable.__getitem__ | getting {key}: {obj}")
            return obj
        else:
            raise KeyError(f"'{key}'")

    def get(self, key):
        fallback = box.Box(dict(zip(self._columns(), (key, *self.defaults))))
        try:
            obj = self[key]
            logger.debug(f"DatabaseTable.get | getting {key}: {obj}")
            return obj
        except KeyError:
            logger.debug(f"DatabaseTable.get | getting {key}: {fallback}; key does not exist")
            return fallback

    def __setitem__(self, key, value):
        if type(value) in (tuple, list):
            # I doubt I'll ever use this directly, but it's here if ever I do.
            if key in self:
                logger.debug(f"DatabaseTable.__setitem__ | setting {key}; full modify")
                for k, v in dict(zip(self._columns(), (key, *value))):
                    self.modify_row(key, k, v)
            else:
                logger.debug(f"DatabaseTable.__setitem__ | setting {key}; full insert")
                self.insert_row(key, value)
        elif type(value) == dict:
            if key in self:
                logger.debug(f"DatabaseTable.__setitem__ | setting {key}; partial modify")
                for k, v in value.items():
                    self.modify_row(key, k, v)
            else:
                logger.debug(f"DatabaseTable.__setitem__ | setting {key}; partial insert")
                self.__setitem__(key, tuple(value.get(*i)
                                            for i in zip([v for v in self._columns()
                                                          if v not in set(self._primary_keys())], self.defaults)))
        else:
            raise TypeError

    def __delitem__(self, key):
        with self.write_mutex as _:
            logger.debug(f"DatabaseTable.__delitem__ | deleting {key}")
            self._execute(f"DELETE FROM {self.table_name} WHERE {self._primary_keys()[0]}=%s", (key,))
            self.__getitem__.cache_clear()
            self.__contains__.cache_clear()

    def __iter__(self):
        return iter(self._execute(f"SELECT {self._primary_keys()[0]} FROM {self.table_name}"))

    @functools.lru_cache()
    def __contains__(self, key):
        ret = bool(self._execute(f"SELECT {self._primary_keys()[0]} FROM {self.table_name} "
                                 f"WHERE {self._primary_keys()[0]}=%s",
                                 (key,)))
        logger.debug(f"DatabaseTable.__contains__ | checking {key}'s existence: "
                     f"{'exists' if ret else 'does not exist'}")
        return ret

    def modify_row(self, key, column, value):
        if column not in self._columns():
            raise ValueError

        with self.write_mutex as _:
            if self[key][column] != value:
                logger.debug(f"DatabaseTable.modify_row | change {key}'s {column} to {value}")
                self._execute(f"""UPDATE {self.table_name}
                    SET {column}=%s
                    WHERE {self._primary_keys()[0]}=%s;
                """, (value, key))
                logger.debug(f"DatabaseTable.modify_row | {key}'s {column} changed to {value}")
            else:
                logger.debug(f"DatabaseTable.modify_row | {key}'s {column} is already {value}")
            self.__getitem__.cache_clear()

    def insert_row(self, key, value):
        logger.debug(f"DatabaseTable.insert_row | inserting row {value} to {key}")
        with self.write_mutex as _:
            self._execute(f"""INSERT INTO {self.table_name}({', '.join(self._columns())})
                             VALUES({', '.join(['%s' if i is not None else 'NULL' for i in (key, *value)])})
                         """, (key, *tuple(i for i in value if i is not None)))
            self.__getitem__.cache_clear()
            self.__contains__.cache_clear()

    @property
    def columns(self):
        logger.debug(f"DatabaseTable.columns | retrieving")
        return self._columns()

    @property
    def primary_keys(self):
        logger.debug(f"DatabaseTable.primary_keys | retrieving")
        return self._primary_keys()

    @property
    def table_info(self):
        logger.debug("DatabaseTable.table_info | retrieving")
        return self._table_info()

    @functools.lru_cache()
    def _columns(self):
        return tuple(i[1] for i in self._table_info())

    @functools.lru_cache()
    def _primary_keys(self):
        return tuple(i[0] for i in sorted(list((i[1], i[5]) for i in self._table_info()
                                               if i[5] != 0), key=lambda x: x[1]))

    @functools.lru_cache()
    def _table_info(self):
        with self.write_mutex as _:
            return self._execute(f"""
                SELECT 
                  col.ORDINAL_POSITION,
                  col.COLUMN_NAME,
                  col.COLUMN_TYPE,
                  col.IS_NULLABLE,
                  col.COLUMN_DEFAULT,
                  ifnull(kcu.ORDINAL_POSITION, 0)
                FROM information_schema.COLUMNS col
                LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu
                    ON col.TABLE_SCHEMA=kcu.TABLE_SCHEMA
                    AND col.TABLE_NAME=kcu.TABLE_NAME
                    AND col.COLUMN_NAME=kcu.COLUMN_NAME
                WHERE col.TABLE_SCHEMA='{self.database.database_name}'
                    AND col.TABLE_NAME='{self.table_name}'
            """)


class UserPrefTable(DatabaseTable):
    def update_last_command(self, key):
        self[key] = {
            "last_command": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
        # "%Y-%m-%dT%H:%M:%S.%f%z"
