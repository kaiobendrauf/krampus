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
    cel_expr: Mapped[str] = mapped_column(String(255))
    custom_msg: Mapped[str] = mapped_column(String(255))
    custom_url: Mapped[str] = mapped_column(String(255))
    identifier: Mapped[str] = mapped_column(String(255))
    notification_app_name: Mapped[str] = mapped_column(String(255))
    policy: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(255))
    server_last_edit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Targets(Base):
    __tablename__ = 'targets'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table: Mapped[str] = mapped_column(String(255))
    linked_id: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(String(255))
    include: Mapped[bool] = mapped_column(Boolean)

class HostClass(Base):
    __tablename__ = 'hostconfigs'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allowed_path_regex: Mapped[str] = mapped_column(String(255))
    batch_size: Mapped[int] = mapped_column(Integer)
    block_usb_mount: Mapped[bool] = mapped_column(Boolean)
    disable_unknown_event_upload: Mapped[bool] = mapped_column(Boolean)
    enable_all_event_upload: Mapped[bool] = mapped_column(Boolean)
    enable_bundles: Mapped[bool] = mapped_column(Boolean)
    enable_transitive_rules: Mapped[bool] = mapped_column(Boolean)
    full_sync_interval: Mapped[int] = mapped_column(Integer)
    override_file_access_action: Mapped[str] = mapped_column(String(255))
    push_notification_full_sync_interval: Mapped[int] = mapped_column(Integer)
    push_notification_global_rule_sync_deadline: Mapped[int] = mapped_column(Integer)

class KrampusInfo(Base):
    __tablename__ = 'krampusinfo'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_rule_delete: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class MachineStatus(Base):
    __tablename__ = 'machinestatus'

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(255), unique=True)
    n_rules_sent: Mapped[int] = mapped_column(Integer)
    sync_type: Mapped[str] = mapped_column(String(255))
    last_check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_clean_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    clean_sync_by: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class UserGroups(Base):
    __tablename__ = 'usergroups'

    row_id: Mapped[int] = mapped_column(primary_key=True)
    linked_id: Mapped[int] = mapped_column(Integer)
    group: Mapped[str] = mapped_column(String(255))


# class Event(Base):
#     __tablename__ = "events_full"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     file_sha256:

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
    if 'row_id' in data:
        if lookup_by_id(collection, data['row_id']):
            return 409, f'Conflict: data with this id ({data["row_id"]}) already exists in {collection}. New data could not be added at this id.)'
    targets = data.pop('targets', None)
    exclusions = data.pop('exclusions', None)
    groups = data.pop('primary_user_groups', None)
    
    with db.connect() as conn:
        result = conn.execute(insert(get_table(collection)).values(**data))
        row_id = result.inserted_primary_key[0]
        conn.commit()

    add_to_lists_database(targets, exclusions, groups, collection, row_id)
    
    logging.debug(f'Added entry {row_id} to {collection}')
    return 200, f'Entry added to {collection}'


def read(collection: str, limit: int, cursor = None) -> dict:
    '''
    Reads multiple rows of data from one collection, optionally starting at some cursor

    Parameters:
        collection: name of the collection to read from
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read (type determined by database)

    Returns:
        dict: dict containing list of data (key="data") and optionally a cursor (key="cursor") if there is more data to read
    '''
    data = get_all_rows(collection, limit=limit+1, cursor=cursor)

    data = [add_lists(row, collection) for row in data]

    if collection == 'rules':
        # this data has server added fields that need to be removed
        for row in data:
            row.pop('server_last_edit_date')
    if len(data) > limit:
        last = data.pop()
        return {'data': data, 'cursor': last['row_id']}
    else:
        return {'data': data}


def read_new_rules(date: datetime, limit: int, cursor = None) -> dict:
    '''
    Reads multiple rows of data from the rules collection that were edited after the given time point

    Parameters:
        date: datetime to read after (not inclusive)
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read (type determined by database)

    Returns:
        dict: dict containing list of rules (key="rules") and optionally a cursor (key="cursor") if there is more data to read
    '''

    tbl = get_table('rules')
    if cursor:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.row_id > cursor).where(tbl.c.server_last_edit_date > date).order_by(tbl.c.row_id).limit(limit+1))
    else:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.server_last_edit_date > date).order_by(tbl.c.row_id).limit(limit+1))
    rows = [dict(row._mapping) for row in rows]

    rows = [add_lists(row, collection) for row in rows]

    # this data has server added fields that need to be removed
    [row.pop('server_last_edit_date') for row in rows]
    
    if len(rows) > limit:
        last = rows.pop()
        return {'data': rows, 'cursor': last['row_id']}
    else:
        return {'data': rows}


def delete(collection: str, data: dict, multiple: bool = False) -> tuple[int, str]:
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
    if collection == 'rules':
        with db.connect() as conn:
            t = get_table('krampusinfo')
            conn.execute(update(t).where(t.c.row_id == 1).values(last_rule_delete=datetime.now(timezone.utc)))
            conn.commit()
    rows = lookup(collection, data)
    if len(rows) == 0:
        return 404, f'Data was not found in {collection} so could not be deleted.'
    if len(rows) == 1:
        delete_row_by_id(collection, rows[0]['row_id'])
        return 200, f'Match found and deleted from {collection}.'
    if multiple:
        for row in rows:
            delete_row_by_id(collection, row['row_id'])
        return 200, f'Multiple ({len(rows)}) matches found in {collection}, all deleted.'
    else:
        return 400, f'Included data has more than one match in {collection}. Please check database and request manually.'


def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns None if no deletion has ever occured 
    row = lookup_by_id('krampusinfo', 1)
    if row:
        return row['last_rule_delete']


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
        data = conn.execute(select(tbl).where(tbl.c.row_id == row_id)).first()
    if data:
        if collection in ['rules', 'hostconfigs', 'machinestatus']:
            return add_lists(dict(data._mapping), collection)
        return dict(data._mapping)


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

    targets = data.pop('targets', None)
    exclusions = data.pop('exclusions', None)
    groups = data.pop('primary_user_groups', None)

    with db.connect() as conn:
            rows = conn.execute(select(tbl).filter_by(**data))
    results = [dict(row._mapping) for row in rows]

    if collection in ['rules', 'hostconfigs', 'machinestatus']:
        results = filter_matches_by_lists(collection, targets, groups, exclusions, results)

    return results

def lookup_hostconfig_by_target(target: str) -> list:
    '''
    Returns all hostconfigs in the collection that apply to a given target

    Parameters:
        targer: the target of the hostconfig

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    rows = lookup('targets', {'table': 'hostconfigs', 'target': target, 'include': True})
    results = []
    row_ids = set()
    for row in rows:
        row_ids.add(row['linked_id'])
    for row_id in list(row_ids):
        results.append(lookup_by_id('hostconfigs', row_id))
    return results


def edit_row(collection: str, data: dict) -> tuple[int, str]:
    '''
    Edits specified row at a given id to match data. 
    For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to edit
        data: new data for that row in the collection, MUST include key 'id'.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if 'row_id' not in data:
        return 400,  f'Row provided does not contain an id, unkown which row to edit.'
    if collection == 'rules':
            data['server_last_edit_date'] = datetime.now(timezone.utc)
    row = lookup_by_id(collection, data['row_id'])
    if row:
        delete_row_by_id(collection, data['row_id'])
        add(collection, data)
        return 200, f'Entry {row["row_id"]} edited in {collection}'
    else:
        return 404, f'Row at id {data["row_id"]} not found in {collection}, so cannot be edited.'

def edit_fields(collection: str, data: dict) -> tuple[int, str]:
    '''
    Edits specified fields in row at a given id updated to match data. 
    For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to edit
        data: new data for that row in the collection, MUST include key 'id'.

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if 'row_id' not in data:
        return 400,  f'Row provided does not contain an id, unkown which row to edit.'
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    
    targets = data.pop('targets', None)
    exclusions = data.pop('exclusions', None)
    groups = data.pop('primary_user_groups', None)
    
    row = lookup_by_id(collection, data['row_id'])
    if row:
        with db.connect() as conn:
            t = get_table(collection)
            conn.execute(update(t).where(t.c.row_id == data['row_id']).values(**data))
            conn.commit()
        add_to_lists_database(targets, exclusions, groups, collection, data['row_id'], True)
        logging.debug(f'Edited entry {data['row_id']} in {collection}')
        return 200, f'Fields in row {data["row_id"]} edited in {collection}.'
    else:
        return 404, f"Data {data["row_id"]} not found in {collection}, so cannot be edited"


def add_or_edit(collection: str, data: dict) -> tuple[int, str]:
    '''
    Edits one row of data to the database, or edits it if the row contains an id and that id already exists. 
    For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to add data to
        data: data for that row in the collection
        row_id: desired id for new row in the collection

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if 'row_id' in data and get_row_by_id(collection, data['row_id']):
        # edit
        return edit_row(collection, data)
    else:
        # add
        return add(collection, data)


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------

def get_table(collection):
    return Table(collection, MetaData(), autoload_with=db)


def get_all_rows(collection, limit=None, cursor=None):
    tbl = get_table(collection)
    if cursor:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).where(tbl.c.row_id > cursor).order_by(tbl.c.row_id).limit(limit))
    else:
        with db.connect() as conn:
            rows = conn.execute(select(tbl).order_by(tbl.c.row_id).limit(limit))
    return [dict(row._mapping) for row in rows]


def delete_row_by_id(collection, i):
    tbl = get_table(collection)
    with db.connect() as conn:
        rows = conn.execute(sqldelete(tbl).where(tbl.c.row_id == i))
        conn.commit()
    logging.debug(f'Deleted row {i} from {collection}.')
    if collection in ['rules', 'hostconfigs']:
        delete('targets', {'table': collection, 'linked_id': i}, True)
    elif collection == 'machinestatus':
        delete('usergroups', {'linked_id': i}, True)

    # for col in cols:
    #     if col.key in data:
    #         stmt.where(col == data[col.key])

    # for k, v in get_column_values(tbl).items():
    #     stmt = stmt.where(getattr(User, k) == v)
    # if cursor:
    #     with db.connect() as conn:
    #         rows = conn.execute(select(tbl).where(tbl.c.row_id > cursor).limit(limit))
    # else:
    #     with db.connect() as conn:
    #         rows = conn.execute(select(tbl).limit(limit))
    # data = []
    # for row in rows:
    #     data.append(dict(row._mapping))
    # return data

def add_lists(data, table):
    if table in ['rules', 'hostconfigs']:
        targets = []
        exclusions = []
        target_data = lookup('targets', {'linked_id': data['row_id'], 'table': table})
        for target in target_data:
            if target['include']:
                targets.append(target['target'])
            else:
                exclusions.append(target['target'])
        if len(targets) > 0:
            data['targets'] = targets
        if len(exclusions) > 0:
            data['exclusions'] = exclusions
    elif table == 'machinestatus':
        groups = lookup('usergroups', {'linked_id': data['row_id']})
        if len(groups) > 0:
            data['primary_user_groups'] = groups
    return data

def add_to_lists_database(targets, exclusions, groups, table, linked_id, delete_old=False):
    if targets:
        if delete_old:
            delete('targets', {'table': table, 'linked_id': linked_id, 'include': True}, True)
        for target in targets:
            add('targets', {'table': table, 'linked_id': linked_id, 'target': target, 'include': True})
    if exclusions:
        if delete_old:
            delete('targets', {'table': table, 'linked_id': linked_id, 'include': False}, True)
        for exclusion in exclusions:
            add('targets', {'table': table, 'linked_id': linked_id, 'target': exclusion, 'include': False})
    if groups:
        if delete_old:
            delete('usergroups', {'linked_id': linked_id})
        for group in groups:
            add('targets', {'linked_id': linked_id, 'group': group})

def filter_matches_by_lists(collection, targets, groups, exclusions, results):
    if collection in ['rules', 'hostconfigs', 'machinestatus']:
        old_results = [add_lists(row, collection) for row in results]
        results = []

        for result in old_results:
            to_add = False
            if targets:
                if 'targets' in result and set(result['targets']) == set(targets):
                    to_add = True
            elif 'targets' not in result:
                to_add = True
            if exclusions:
                if 'exclusions' in result and set(result['exclusions']) == set(exclusions):
                    to_add = True
            elif 'exclusions' not in result:
                to_add = True
            if groups:
                if 'primary_user_groups' in result and set(result['primary_user_groups']) == set(groups):
                    to_add = True
            elif 'primary_user_groups' not in result:
                to_add = True
            if to_add:
                results.append(result)
    return results