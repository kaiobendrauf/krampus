import logging
import os
import sys
import uuid

from datetime import datetime, timezone
from google.cloud import firestore

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------

def setup():
    # Sets up the database object, checking that environmental variables 'GCP_PROJ_ID' 'DB_NAME' and are found
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

def add(collection: str, data: dict, row_id: str=None) -> tuple[int, str]:
    '''
    Adds one row of data to the database, optionally at some specific row id. For the "rules" collection the datetime a rule is added is tracked.

    Parameters:
        collection: name of the collection to add data to
        data: data for that row in the collection
        row_id: desired id for new row in the collection

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    if row_id:
        db.collection(collection).document(row_id).set(data)
        return 200, f'Entry added to {collection}'
    matches = list(get_doc_by_match(collection, data))
    if len(matches) == 0:
        doc = get_new_doc_id(collection)
        db.collection(collection).document(doc).set(data)
        return 200, f'Entry added to {collection}'
    else:
        return 200, f'Data already found in {collection}, so was not added.'

def read(collection: str, limit: int, cursor: str=None) -> dict:
    '''
    Reads multiple rows of data from one collection, optionally starting at some cursor

    Parameters:
        collection: name of the collection to read from
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read

    Returns:
        dict: dict containing list of data (key="data") and optionally a cursor (key="cursor") if there is more data to read
    '''
    data, cursor = get_all_docs(collection, limit, cursor)
    if data:
        if collection == 'rules':
            # this data has server added fields that need to be removed
            for row in data:
                row.pop('server_last_edit_date')
        if cursor:
            return {'data': data, 'cursor': cursor}
        else:
            return {'data': data}
    return {'data': []}

def read_new_rules(date: datetime, limit: int, cursor: str=None) -> dict:
    '''
    Reads multiple rows of data from the rules collection that were edited after the given time point

    Parameters:
        date: datetime to read after (not inclusive)
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read

    Returns:
        dict: dict containing list of rules (key="rules") and optionally a cursor (key="cursor") if there is more data to read
    '''
    data, cursor = get_all_docs_by_filter('rules', [('server_last_edit_date', '>', date)], limit=limit, cursor=cursor)
    if data:
        # this data has server added fields that need to be removed
        for row in data:
            row.pop('server_last_edit_date')
    else:
        data = []
    if data and cursor:
        return {"rules": data, "cursor": cursor}
    else:
        return {'rules': data}

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
    if collection == 'rules':
        db.collection('machine_status').document('last_rule_delete').set({'date': datetime.now(timezone.utc)})
    docs = list(get_doc_by_match(collection, data))
    if len(docs) == 0:
        return 404, f'Data was not found in {collection} so could not be deleted.'
    if len(docs) == 1:
        db.collection(collection).document(docs[0].id).delete()
        return 200, f'Match found and deleted from {collection}.'
    if multiple:
        for doc in docs:
            db.collection(collection).document(doc.id).delete()
        return 200, f'Multiple matches found in {collection}, all deleted.'
    else:
        return 400, f'Included data has more than one match in {collection}. Please check database and request manually.'

def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns None if no deletion has ever occured 
    doc = get_doc_by_id('machine_status', 'last_rule_delete')
    if doc.exists:
        return doc.to_dict()['date']
    else:
        return None

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
    result = get_doc_by_id(collection, row_id)
    if not result.exists:
        return None
    return result.to_dict()

def lookup(collection: str, data: dict) -> list:
    '''
    Returns all rows in the collection matching the given data

    Parameters:
        collection: name of the collection to read from
        data: every key value pair in data should exist in all returned rows

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    result = list(get_doc_by_match(collection, data))
    result = [doc.to_dict() for doc in result]
    return result

def edit(collection: str, data: dict, row_id: str) -> tuple[int, str]:
    '''
    Edits specified row to match data. For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to edit
        data: new data for that row in the collection
        row_id: id of row ro edit

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    doc = get_doc_by_id(collection, row_id)
    if doc.exists:
        if collection == 'rules':
            data['server_last_edit_date'] = datetime.now(timezone.utc)
        db.collection(collection).document(row_id).set(data)
        return 200, f'Entry {row_id} edited in {collection}'
    else:
        return 404, f"Data {row_id} not found in {collection}, so cannot be edited"

def add_or_edit(collection: str, data: dict, row_id: str) -> tuple[int, str]:
    '''
    Edits one row of data to the database, or edits it if the row id already exists. For the "rules" collection the datetime a rule is added / edited is tracked.

    Parameters:
        collection: name of the collection to add data to
        data: data for that row in the collection
        row_id: desired id for new row in the collection

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    if collection == 'rules':
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    db.collection(collection).document(row_id).set(data)
    return 200, f'Entry added to (or edited in) {collection}'


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------
def get_new_doc_id(collection):
    while True:
        result = str(uuid.uuid4())
        if not get_doc_by_id(collection, result).exists:
            return result

def get_doc_by_id(collection, doc):
    doc_ref = db.collection(collection).document(doc)
    return doc_ref.get()

def get_doc_by_match(collection, data):
    query_ref = db.collection(collection)
    for key in data:
        # Create a query against the collection
        query_ref = query_ref.where(filter=firestore.FieldFilter(key, "==", data[key]))
    results = query_ref.stream()
    return results

def get_all_docs(collection, limit=None, cursor=None):
    if limit:
        if cursor:
            cursor_doc = get_doc_by_id(collection, cursor)
            query = db.collection(collection).start_after(cursor_doc).limit(limit+1)
        else:
            query = db.collection(collection).limit(limit+1)
        docs = list(query.stream())
        if len(docs) > 0:
            if len(docs) > limit:
                # more to read
                docs = docs[:-1]
                last_doc = list(docs)[-1]
                return [doc.to_dict() for doc in docs], last_doc.id
            else:
                # done reading
                return [doc.to_dict() for doc in docs], None
        else:
            return None, None
    else:
        docs = db.collection(collection).stream()
        return [doc.to_dict() for doc in docs], None

def get_all_docs_by_filter(collection, filters, limit=None, cursor=None):
    # create query
    query = db.collection(collection)
    if cursor:
        query.start_after(cursor)
    if limit:
        query.limit(limit+1)
    # add filters
    for key, comp, val in filters:
        # Create a query against the collection
        query = query.where(filter=firestore.FieldFilter(key, comp, val))
    docs = list(query.stream())
    if len(docs) > 0:
        if len(docs) > limit:
            # more to read
            docs = docs[:-1]
            last_doc = list(docs)[-1]
            return [doc.to_dict() for doc in docs], last_doc.id
        else:
            # done reading
            return [doc.to_dict() for doc in docs], None
    else:
        return None, None