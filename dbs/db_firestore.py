import logging
import os
import sys

from datetime import datetime, timezone
from google.cloud import firestore

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------

def setup():
    # Sets up the database object, checking that environmental variables 'GCP_PROJ_ID', and 'DB_NAME' are found
    gcp_proj_id = os.environ.get('GCP_PROJ_ID')
    db_name = os.environ.get('DB_NAME')

    if not gcp_proj_id:
        logging.error('A GCP project id is required to connect to a firestore database, please add this as the environmental variable "GCP_PROJ_ID".')
        sys.exit(1)
    if not db_name:
        logging.error('A database name id is required to connect to a firestore database, please add this as the environmental variable "DB_NAME".')
        sys.exit(1)

    global db
    db = firestore.Client(project=gcp_proj_id, database=db_name)
    logging.debug(f"Successfully created Firestore client in GCP project: {db.project}")

    if lookup_by_id('krampusinfo', '1') is None:
        db.collection('krampusinfo').document('1').set({'last_rule_delete': datetime.now(timezone.utc), 'block_preflight': False, 'block_ruledownload': False})


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
        else:
            db.collection(collection).document(str(data['row_id'])).set(data)
    else:
        update_time, row = db.collection(collection).add(data)
        row.update({'row_id': row.id})
        data['row_id'] = row.id
    return 200, f'Entry added to {collection} with row_id {data['row_id']}'


def block_sync(collection: str) -> tuple[int, str]:
    '''
    Blocks either preflight or rule download stages of the sync, while the relevant collection is edited.

    Parameters:
        collection: name of the collection that should not be used for the sync

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if collection == 'hostconfigs':
        edit_fields('krampusinfo', {'block_preflight': True})
        logging.info('Preflight blocked.')
        return 200, 'Blocked Preflight'
    elif collection == 'rules':
        edit_fields('krampusinfo', {'block_ruledownload': True})
        logging.info('Rule Download blocked.')
        return 200, 'Rule download blocked.'
    else:
        return 400, 'Invalid collection given to block sync.'


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
    docs = lookup(collection, data)
    if len(docs) == 0:
        return 404, f'Data was not found in {collection} so could not be deleted.'
    if len(docs) == 1:
        delete_doc_by_id(collection, docs[0]['row_id'])
        return 200, f'Match found at row_id {docs[0]["row_id"]} and deleted from {collection}.'
    if multiple:
        for doc in docs:
            delete_doc_by_id(collection, doc['row_id'])
        return 200, f'Multiple ({len(docs)}) matches found in {collection} at row_ids: {str([doc["row_id"] for doc in docs])[1:-1]}. All deleted.'
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
        return 400,  f'Row provided does not contain a row_id, unknown which row to edit.'
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    
    row = lookup_by_id(collection, data['row_id'])
    if row:
        db.collection(collection).document(str(data['row_id'])).update(data)
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
        return 400,  f'Row provided does not contain a row_id, unknown which row to edit.'
    if collection == 'rules':
            data['server_last_edit_date'] = datetime.now(timezone.utc)
    row = lookup_by_id(collection, data['row_id'])
    if row:
        logging.debug(f'Edited entry {data['row_id']} in {collection}')
        db.collection(collection).document(str(data['row_id'])).set(data)
        return 200, f'Entry {row["row_id"]} edited in {collection}'
    else:
        return 404, f'Row at row_id {data["row_id"]} not found in {collection}, so cannot be edited.'


def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns time of database creation if no deletion has ever occurred
    doc = lookup_by_id('krampusinfo', '1')
    if doc:
        return doc['last_rule_delete']


def is_sync_stage_blocked(stage: str) -> bool:
    '''
    Check whether the named sync stage is blocked

    Parameters:
        stage: can be 'preflight', 'eventupload,' 'ruledownload', 'postflight'

    Returns:
        bool: whether the named sync stage is blocked
    '''

    if stage not in ['preflight', 'eventupload', 'ruledownload', 'postflight']:
        logging.warning(f'Checking if sync stage {stage} is blocked, but this is not a valid stage of the sync.')
        return False

    if stage not in ['eventupload', 'postflight']:
        return False

    return lookup_by_id('krampusinfo', '1')['block_' + stage]


def lookup(collection: str, data: dict) -> list:
    '''
    Returns all rows in the collection matching the given data

    Parameters:
        collection: name of the collection to read from
        data: every key value pair in data should exist in all returned rows

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    query = db.collection(collection)
    for key in data:
        # Create a query against the collection
        query = query.where(filter=firestore.FieldFilter(key, '==', data[key]))
    docs = query.stream()
    return [doc.to_dict() for doc in list(docs)]


def lookup_by_id(collection: str, row_id) -> dict | None:
    '''
    Returns the row in the collection matching the row id

    Parameters:
        collection: name of the collection to read from
        row_id: id of row to return

    Returns:
        dict: dict containing data at the given row id
              returns None if no such row is found
    '''
    doc = db.collection(collection).document(str(row_id)).get()
    if doc.exists:
        return doc.to_dict()


def lookup_hostconfig_by_target(target: str) -> list:
    '''
    Returns all hostconfigs in the collection that apply to a given target

    Parameters:
        target: the target of the hostconfig

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    query = db.collection('hostconfigs').where(filter=firestore.FieldFilter('targets', 'array_contains', target))
    docs = query.stream()
    return [doc.to_dict() for doc in list(docs)]

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
    docs = get_all_docs(collection, limit+1, cursor)

    if collection == 'rules':
        # this data has server added fields that need to be removed
        for doc in docs:
            doc.pop('server_last_edit_date')
    if len(docs) > limit:
        docs.pop()
        return {'data': docs, 'cursor': docs[-1]['row_id']}
    else:
        return {'data': docs}


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
    if cursor:
        cursor_doc = db.collection('rules').document(str(cursor)).get()
        docs = db.collection('rules').start_after(cursor_doc).limit(limit+1).where(filter=firestore.FieldFilter('server_last_edit_date', '>', date)).stream()
    else:
        docs = db.collection('rules').limit(limit+1).where(filter=firestore.FieldFilter('server_last_edit_date', '>', date)).stream()
    
    docs = [doc.to_dict() for doc in list(docs)]
    # this data has server added fields that need to be removed
    for doc in docs:
        doc.pop('server_last_edit_date')
    
    if len(docs) > limit:
        docs.pop()
        return {'data': docs, 'cursor': docs[-1]['row_id']}
    else:
        return {'data': docs}


def unblock_sync(collection: str) -> tuple[int, str]:
    '''
    Unblocks either preflight or rule download stages of the sync, as the relevant collection is no longer being edited.

    Parameters:
        collection: name of the collection that should not be used for the sync

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if collection == 'hostconfigs':
        edit_fields('krampusinfo', {'block_preflight': False})
        logging.info('Preflight unblocked.')
        return 200, 'Unblocked Preflight'
    elif collection == 'rules':
        edit_fields('krampusinfo', {'block_ruledownload': False})
        logging.info('Rule Download unblocked.')
        return 200, 'UnblockedRule download.'
    else:
        return 400, 'Invalid collection given to block sync.'

# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------
def delete_doc_by_id(collection, row_id):
    db.collection(collection).document(str(row_id)).delete()
    logging.debug(f'Deleted row {row_id} from {collection}.')
    store_delete_time(collection)

def get_all_docs(collection, limit=None, cursor=None):
    query = db.collection(collection)
    if cursor:
        cursor_doc = db.collection(collection).document(str(cursor)).get()
        query = query.start_after(cursor_doc)
    if limit:
        query = query.limit(limit)
    docs = query.stream()
    return [doc.to_dict() for doc in list(docs)]

def store_delete_time(collection):
    if collection == 'rules':
        db.collection('krampusinfo').document('1').update({'last_rule_delete': datetime.now(timezone.utc)})


