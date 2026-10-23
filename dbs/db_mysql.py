import logging
import os
import sys

from datetime import datetime

from . import sqlalchemy_util

db = None

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------

def setup():
    # Sets up the database object, checking that environmental variables 'MYSQL_HOST', 'DB_NAME', MYSQL_USER, and MYSQL_PW are found

    db_host = os.environ.get('MYSQL_HOST')
    db_name = os.environ.get('DB_NAME')
    db_port = os.environ.get('MYSQL_PORT')
    db_user = os.environ.get('MYSQL_USER')
    db_password = os.environ.get('MYSQL_PW')

    if not db_name:
        logging.error('You need to specify the database name to use, using the "DB_NAME" environment variable.')
        sys.exit(1)
    if not db_host:
        logging.error('You need to specify the database host to use, using the "MYSQL_HOST" environment variable.')
        sys.exit(1)
    if not db_port:
        # default to 3306
        db_port = 3306
    if not db_user:
        logging.error('You need to specify the MySQL user to use, using the "MYSQL_USER" environment variable.')
        sys.exit(1)
    if not db_password:
        logging.error(
            'You need to specify the password for your MySQL user, using the "MYSQL_PW" environment variable.')
        sys.exit(1)

    connection_string = f"mysql+mysqlconnector://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    sqlalchemy_util.setup_engine(connection_string)
    sqlalchemy_util.setup()


def add(collection: str, data: dict) -> tuple[int, str]:
    '''
    Adds one row of data to the database. 
    For the "rules" collection, the datetime a rule is added is tracked.
    All rows for all collections are given a 'row_id' if one is not provided.

    Parameters:
        collection: name of the collection to add data to
        data: data for that row in the collection

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.add(collection, data)


def block_sync() -> tuple[int, str]:
    '''
    Blocks the sync while the database is edited.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.block_sync(collection)


def delete(collection: str, data: dict, multiple: bool=False) -> tuple[int, str]:
    '''
    Deletes data from the database that matches data given. For the "rules" collection, the datetime of the last delete action is stored 

    Parameters:
        collection: name of the collection to add data to
        data: data to be deleted, rows that contain all key value pairs in this dictionary will be deleted
        multiple: whether multiple rows should be deleted if data matches multiple rows
                  when set to False, no data is deleted if multiple matches are found

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.delete(collection, data, multiple)


def edit_fields(collection: str, data: dict) -> tuple[int, str]:
    '''
    Edits specified fields in row. 
    Assumes data contains 'row_id' and that the row at 'row_id' exists.
    For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to edit
        data: new data for that row in the collection, MUST include key 'row_id'.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.edit_fields(collection, data)


def edit_row(collection: str, data: dict) -> tuple[int, str]:
    '''
    Edits specified row in collection.
    Assumes data contains 'row_id' and that the row at 'row_id' exists.
    For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to edit
        data: new data for that row in the collection, MUST include key 'row_id'.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.edit_row(collection, data)


def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns time of database creation if no deletion has ever occurred
    return sqlalchemy_util.get_last_rule_delete()


def is_sync_blocked() -> bool:
    '''
    Check whether the sync is blocked

    Returns:
        bool: whether the named sync stage is blocked
    '''
    return sqlalchemy_util.is_sync_blocked()


def lookup(collection: str, data: dict) -> list:
    '''
    Returns all rows in the collection matching the given data

    Parameters:
        collection: name of the collection to read from
        data: every key value pair in data should exist in all returned rows

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    return sqlalchemy_util.lookup(collection, data)


def lookup_by_id(collection: str, row_id: str) -> dict | None:
    '''
    Returns the row in the collection matching the row id

    Parameters:
        collection: name of the collection to read from
        row_id: id of row to return

    Returns:
        dict: dict containing data at the given row id
              returns None if no such row is found
    '''
    return sqlalchemy_util.lookup_by_id(collection, row_id)


def lookup_hostconfig_by_target(target: str) -> list:
    '''
    Returns all hostconfigs in the collection that apply to a given target

    Parameters:
        target: the target of the hostconfig

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    return sqlalchemy_util.lookup_hostconfig_by_target(target)


def read(collection: str, limit: int, cursor = None) -> dict:
    '''
    Reads multiple rows of data from one collection, optionally starting at some cursor

    Parameters:
        collection: name of the collection to read from
        limit: how many rows of data to read
        cursor: optional cursor so that only data after cursor is read (type determined by database)

    Returns:
        dict: dict containing list of data (key="data") and optionally a cursor (key="cursor") if there is more data to read
    '''
    return sqlalchemy_util.read(collection, limit, cursor)


def read_new_rules(date: datetime, limit: int, cursor = None) -> dict:
    '''
    Reads multiple rows of data from the rules collection that were edited after the given time point

    Parameters:
        date: datetime to read after (not inclusive)
        limit: how many rows of data to read
        cursor: optional cursor so that only data after cursor is read (type determined by database)

    Returns:
        dict: dict containing list of rules (key='rules') and optionally a cursor (key='cursor') if there is more data to read
    '''
    return sqlalchemy_util.read_new_rules(date, limit, cursor)


def unblock_sync() -> tuple[int, str]:
    '''
    Unblocks the sync, as the database is no longer being edited.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    return sqlalchemy_util.unblock_sync(collection)

