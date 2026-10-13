import logging
import os
import sys

from datetime import datetime, timezone
from sqlalchemy import delete as sqldelete
from sqlalchemy import Boolean, create_engine, DateTime, insert, Integer, MetaData, select, String, Table, text, update
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, Session
from sqlalchemy.testing.schema import mapped_column

db = None
'''
ORM Types
'''

class Base(DeclarativeBase):
    pass

class Rule(Base):
    __tablename__ = 'rules'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cel_expr: Mapped[str] = mapped_column(String(255), nullable=True)
    custom_msg: Mapped[str] = mapped_column(String(255), nullable=True)
    custom_url: Mapped[str] = mapped_column(String(255), nullable=True)
    identifier: Mapped[str] = mapped_column(String(255))
    notification_app_name: Mapped[str] = mapped_column(String(255), nullable=True)
    policy: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(255))
    server_last_edit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Lists(Base):
    __tablename__ = 'lists'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    linked_table: Mapped[str] = mapped_column(String(255))
    linked_id: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(255))

class HostClass(Base):
    __tablename__ = 'hostconfigs'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allowed_path_regex: Mapped[str] = mapped_column(String(255), nullable=True)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=True)
    block_usb_mount: Mapped[bool] = mapped_column(Boolean, nullable=True)
    disable_unknown_event_upload: Mapped[bool] = mapped_column(Boolean, nullable=True)
    enable_all_event_upload: Mapped[bool] = mapped_column(Boolean, nullable=True)
    enable_bundles: Mapped[bool] = mapped_column(Boolean, nullable=True)
    enable_transitive_rules: Mapped[bool] = mapped_column(Boolean, nullable=True)
    full_sync_interval: Mapped[int] = mapped_column(Integer, nullable=True)
    override_file_access_action: Mapped[str] = mapped_column(String(255), nullable=True)
    push_notification_full_sync_interval: Mapped[int] = mapped_column(Integer, nullable=True)
    push_notification_global_rule_sync_deadline: Mapped[int] = mapped_column(Integer, nullable=True)

class KrampusInfo(Base):
    __tablename__ = 'krampusinfo'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_rule_delete: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class MachineStatus(Base):
    __tablename__ = 'machinestatus'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(255), unique=True)
    primary_user: Mapped[str] = mapped_column(String(255))
    n_rules_sent: Mapped[int] = mapped_column(Integer)
    sync_type: Mapped[str] = mapped_column(String(255))
    last_check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_clean_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    clean_sync_by: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


# class UserGroups(Base):
#     __tablename__ = 'usergroups'

#     row_id: Mapped[int] = mapped_column(primary_key=True)
#     linked_id: Mapped[int] = mapped_column(Integer)
#     group: Mapped[str] = mapped_column(String(255))


# class Event(Base):
#     __tablename__ = "events_full"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     file_sha256:

class EventSummary(Base):
    __tablename__ = 'eventssummary'

    row_id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    DECISION_UNKNOWN: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_UNKNOWN: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_BINARY: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_CERTIFICATE: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_SCOPE: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_TEAMID: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_SIGNINGID: Mapped[int] = mapped_column(Integer, nullable=True)
    ALLOW_CDHASH: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_UNKNOWN: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_BINARY: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_CERTIFICATE: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_SCOPE: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_TEAMID: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_SIGNINGID: Mapped[int] = mapped_column(Integer, nullable=True)
    BLOCK_CDHASH: Mapped[int] = mapped_column(Integer, nullable=True)
    BUNDLE_BINARY: Mapped[int] = mapped_column(Integer, nullable=True)

def setup_engine(connection_string, echo=True):
    engine = create_engine(connection_string)

    global db
    db = engine

    # create tables if do not already exist
    Base.metadata.create_all(db)

    return db

def setup():
    if len(get_all_rows('krampusinfo')) < 1:
        with db.connect() as conn:
            conn.execute(insert(get_table('krampusinfo')).values(row_id=1, last_rule_delete=datetime.now(timezone.utc)))
            conn.commit()


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
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    if collection == 'hostconfigs' and set(data.keys()).issubset({'targets', 'exclusions', 'remount_usb_mode'}):
            data['batch_size'] = None
    if 'row_id' in data:
        if lookup_by_id(collection, data['row_id']):
            return 409, f'Conflict: data with this id ({data["row_id"]}) already exists in {collection}. New data could not be added at this id.)'
    lists = create_list_dict(data)

    with db.connect() as conn:
        result = conn.execute(insert(get_table(collection)).values(**data))
        row_id = result.inserted_primary_key[0]
        conn.commit()

    add_to_lists_database(collection, row_id, lists)
    
    logging.debug(f'Added entry {row_id} to {collection}')
    return 200, f'Entry added to {collection} at row_id {row_id}'

# def add_or_edit(collection: str, data: dict) -> tuple[int, str]:
#     '''
#     Adds one row of the database, or edits it if data contains an row_id and that row_id already exists in the database. 
#     For the "rules" collection the datetime a rule is added / edited is tracked.

#     Parameters:
#         collection: name of the collection to add data to
#         data: data to get updated in that row in the collection

#     Returns:
#         int: http status code reflecting the success of the attempted action
#         str: description of action taken
#     '''
#     if 'row_id' in data and lookup_by_id(collection, data['row_id']):
#         # edit
#         return edit_row(collection, data)
#     else:
#         # add
#         return add(collection, data)


def delete(collection: str, data: dict, multiple: bool=False) -> tuple[int, str]:
    '''
    Deletes data from the database that matches data given. For the "rules" collection, the datetime of the last delete action is stored 

    Parameters:
        collection: name of the collection to add data to
        data: data to be deleted, rows that contain all key value pairs in this dictionary will be deleted
        multiple: whether multiple rows should be deleted if data matches multiple rows
                  when set to False, no data is deleted if multilpe matches are found

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    rows = lookup(collection, data)
    if len(rows) == 0:
        return 404, f'Data was not found in {collection} so could not be deleted.'
    if len(rows) == 1:
        delete_row_by_id(collection, rows[0]['row_id'])
        return 200, f'Match found at row_id {rows[0]["row_id"]} and deleted from {collection}.'
    if multiple:
        for row in rows:
            delete_row_by_id(collection, row['row_id'])
        return 200, f'Multiple ({len(rows)}) matches found in {collection} at row_ids: {str([row["row_id"] for row in rows])[1:-1]}. All deleted.'
    else:
        return 400, f'Included data has more than one match in {collection}. Please check database and request manually.'


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
    if 'row_id' not in data:
        return 400,  f'Row provided does not contain a row_id, unkown which row to edit.'
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    lists = create_list_dict(data)
    
    row = lookup_by_id(collection, data['row_id'])
    if row:
        with db.connect() as conn:
            t = get_table(collection)
            conn.execute(update(t).where(t.c.row_id == data['row_id']).values(**data))
            conn.commit()
        add_to_lists_database(collection, data['row_id'], lists, True)
        logging.debug(f'Edited fields of {data['row_id']} in {collection}')
        return 200, f'Fields in row {data["row_id"]} edited in {collection}.'
    else:
        return 404, f"Row at row_id {data["row_id"]} not found in {collection}, so cannot be edited"


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
    if 'row_id' not in data:
        return 400,  f'Row provided does not contain a row_id, unkown which row to edit.'
    if collection == 'rules':
            data['server_last_edit_date'] = datetime.now(timezone.utc)
    row = lookup_by_id(collection, data['row_id'])
    if row:
        delete_row_by_id(collection, data['row_id'])
        add(collection, data)
        return 200, f'Entry {row["row_id"]} edited in {collection}'
    else:
        return 404, f'Row at row_id {data["row_id"]} not found in {collection}, so cannot be edited.'

def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns time of database creation if no deletion has ever occured 
    row = lookup_by_id('krampusinfo', 1)
    if row:
        return row['last_rule_delete']


def lookup(collection: str, data: dict) -> list:
    '''
    Returns all rows in the collection matching the given data

    Parameters:
        collection: name of the collection to read from
        data: every key value pair in data should exist in all returned rows

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    tbl = get_table(collection)

    lists = create_list_dict(data)

    with db.connect() as conn:
        rows = conn.execute(select(tbl).filter_by(**data))
    rows = [remove_nulls_from_dict(dict(row._mapping)) for row in rows]

    if collection in ['rules', 'hostconfigs', 'machinestatus']:
        rows = filter_matches_by_lists(collection, lists, rows)

    return rows


def lookup_by_id(collection: str, row_id: str) -> dict:
    '''
    Returns the row in the collection matching the row id

    Parameters:
        collection: name of the collection to read from
        row_id: id of row to return

    Returns:
        dict: dict containing data at the given row id
              returns None if no such row is found
    '''
    tbl = get_table(collection)
    with db.connect() as conn:
        row = conn.execute(select(tbl).where(tbl.c.row_id == row_id)).first()
    if row:
        if collection in ['rules', 'hostconfigs', 'machinestatus']:
            return add_lists(collection, remove_nulls_from_dict(dict(row._mapping)))
        return remove_nulls_from_dict(dict(row._mapping))


def lookup_hostconfig_by_target(target: str) -> list:
    '''
    Returns all hostconfigs in the collection that apply to a given target

    Parameters:
        targer: the target of the hostconfig

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    rows = lookup('lists', {'linked_table': 'hostconfigs', 'key': 'targets', 'value': target})
    results = []
    row_ids = set()
    for row in rows:
        row_ids.add(row['linked_id'])
    for row_id in row_ids:
        results.append(lookup_by_id('hostconfigs', row_id))
    return results


def read(collection: str, limit: int, cursor = None) -> dict:
    '''
    Reads multiple rows of data from one collection, optionally starting at some cursor

    Parameters:
        collection: name of the collection to read from
        limit: how many rows of data to read
        cursor: optional cursor so that only data after cursor is read (type determined by database)

    Returns:
        dict: dict containing list of data (key='data') and optionally a cursor (key='cursor') if there is more data to read
    '''
    rows = get_all_rows(collection, limit=limit+1, cursor=cursor)

    rows = [add_lists(collection, row) for row in rows]

    if collection == 'rules':
        # this data has server added fields that need to be removed
        for row in rows:
            row.pop('server_last_edit_date')
    if len(rows) > limit:
        rows.pop()
        return {'data': rows, 'cursor': rows[-1]['row_id']}
    else:
        return {'data': rows}


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
    tbl = get_table('rules')
    if cursor:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.row_id > cursor).where(tbl.c.server_last_edit_date > date).order_by(tbl.c.row_id).limit(limit+1))
    else:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.server_last_edit_date > date).order_by(tbl.c.row_id).limit(limit+1))
    rows = [remove_nulls_from_dict(dict(row._mapping)) for row in rows]

    rows = [add_lists('rules', row) for row in rows]

    # this data has server added fields that need to be removed
    for row in rows:
        row.pop('server_last_edit_date')
    
    if len(rows) > limit:
        rows.pop()
        return {'data': rows, 'cursor': rows[-1]['row_id']}
    else:
        return {'data': rows}


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------
def add_lists(collection, data):
    if collection in ['hostconfigs', 'rules', 'machinestatus']:
        rows = lookup('lists', {'linked_table': collection, 'linked_id': data['row_id']})
        d = dict()
        for row in rows:
            key = row['key']
            value = row['value']
            if key in d:
                d[key].append(value)
            else:
                d[key] = [value]
        for key in d:
            data[key] = d[key]
    return data

def add_to_lists_database(collection, linked_id, lists, delete_old=False):
    for key in lists:
        if delete_old:
            delete('lists', {'linked_table': collection, 'linked_id': linked_id, 'key': key}, True)
        if not (lists[key] is None):
            if isinstance(lists[key], list):
                for s in lists[key]:
                    add('lists', {'linked_table': collection, 'linked_id': linked_id, 'key': key, 'value': s})
            else:
                logging.error(f'{lists[key]} should be a list of strings, instead it is a {type(lists[key])}. Cannot add to lists database.')

def create_list_dict(data):
    result = dict()
    for key in ['targets', 'exclusions', 'primary_user_groups', 'remount_usb_mode']:
        if key in data:
            result[key] = data.pop(key)
    return result

def delete_row_by_id(collection, i):
    tbl = get_table(collection)
    with db.connect() as conn:
        rows = conn.execute(sqldelete(tbl).where(tbl.c.row_id == i))
        conn.commit()
    logging.debug(f'Deleted row {i} from {collection}.')
    if collection in ['rules', 'hostconfigs', 'machinestatus']:
        delete('lists', {'linked_table': collection, 'linked_id': i}, True)
    store_delete_time(collection)

def filter_matches_by_lists(collection, lists, matches):
    if collection in ['rules', 'hostconfigs', 'machinestatus']:
        results = [add_lists(collection, row) for row in matches]
        matches = []
        for result in results:
            is_match = True
            for key in lists:
                val = lists[key]
                if val is None:
                    if key in result and result[key] is not None:
                        is_match = False
                elif (not (key in result)) or (set(result[key]) != set(val)):
                    is_match = False   
            if is_match:
                matches.append(result)
    return matches

def get_all_rows(collection, limit=None, cursor=None):
    tbl = get_table(collection)
    if cursor:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.row_id > cursor).order_by(tbl.c.row_id).limit(limit))
    else:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).order_by(tbl.c.row_id).limit(limit))
    return [remove_nulls_from_dict(dict(row._mapping)) for row in rows]

def remove_nulls_from_dict(d):
    result = dict()
    for k in d:
        if not (d[k] is None):
            result[k] = d[k]
    return result

def get_table(collection):
    return Table(collection, MetaData(), autoload_with=db)

def store_delete_time(collection):
    if collection == 'rules':
        with db.connect() as conn:
            t = get_table('krampusinfo')
            conn.execute(update(t).where(t.c.row_id == 1).values(last_rule_delete=datetime.now(timezone.utc)))
            conn.commit()
