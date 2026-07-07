import logging
import os
import sys

from datetime import datetime, timezone

from . import sqlalchemy_util

db = None

is_event_handler = True

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------

def setup():
    # Sets up the database object, checking that environmental variables 'MYSQL_HOST', 'DB_NAME', MYSQL_USER, and MYSQL_PW are found

    db_host = os.environ.get('POSTGRES_HOST')
    db_name = os.environ.get('DB_NAME')
    db_port = os.environ.get('POSTGRES_PORT', '5432')
    db_user = os.environ.get('POSTGRES_USER')
    db_password = os.environ.get('POSTGRES_PW')

    if not db_name:
        logging.error('You need to specify the database name to use, using the "DB_NAME" environment variable.')
        sys.exit(1)
    if not db_host:
        logging.error('You need to specify the database host to use, using the "POSTGRES_HOST" environment variable.')
        sys.exit(1)
    if not db_user:
        logging.error('You need to specify the PostgreSQL user to use, using the "POSTGRES_USER" environment variable.')
        sys.exit(1)
    if not db_password:
        logging.error(
            'You need to specify the password for your PostgreSQL user, using the "POSTGRES_PW" environment variable.')
        sys.exit(1)

    connection_string = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    sqlalchemy_util.setup_engine(connection_string)


def add(collection: str, data: dict, row_id: str = None) -> tuple[int, str]:
    '''
    Adds one row of data to the database, optionally at some specific row id. For the "rules" collection, the datetime a rule is added is tracked.

    Parameters:
        collection: name of the collection to add data to
        data: data for that row in the collection
        row_id: desired id for new row in the collection

    Returns:
        int: http status code reflecting the success of the attempted action
        str: description of action taken
    '''
    sqlalchemy_util.add(collection, data, row_id)
    # if table == 'rules':
    #     data['server_last_edit_date'] = datetime.now(timezone.utc)
    # if row_id:
    #     if db:
    #         with db.connect() as conn:
    #             conn.execute()
    #     db.collection(collection).document(row_id).set(data)
    #     return 200, f'Entry added to {collection}'
    # matches = list(get_doc_by_match(collection, data))
    # if len(matches) == 0:
    #     doc = get_new_doc_id(collection)
    #     db.collection(collection).document(doc).set(data)
    #     return 200, f'Entry added to {table}'
    # else:
    #     return 200, f'Data already found in {table}, so was not added.'


def read(collection: str, limit: int, cursor: str = None) -> dict:
    '''
    Reads multiple rows of data from one collection, optionally starting at some cursor

    Parameters:
        collection: name of the collection to read from
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read

    Returns:
        dict: dict containing list of data (key="data") and optionally a cursor (key="cursor") if there is more data to read
    '''
    sqlalchemy_util.read(collection, limit, cursor)
    # data, cursor = get_all_docs(collection, limit, cursor)
    # if data:
    #     if collection == 'rules':
    #         # this data has server added fields that need to be removed
    #         for row in data:
    #             row.pop('server_last_edit_date')
    #     if cursor:
    #         return {'data': data, 'cursor': cursor}
    #     else:
    #         return {'data': data}
    # return {'data': []}


def read_new_rules(date: datetime, limit: int, cursor: str = None) -> dict:
    '''
    Reads multiple rows of data from the rules collection that were edited after the given time point

    Parameters:
        date: datetime to read after (not inclusive)
        limit: how many rows of data to read
        cursor: cursor so that only data after cursor is read

    Returns:
        dict: dict containing list of rules (key="rules") and optionally a cursor (key="cursor") if there is more data to read
    '''
    sqlalchemy_util.read(date, limit, cursor)
    # data, cursor = get_all_docs_by_filter('rules', [('server_last_edit_date', '>', date)], limit=limit, cursor=cursor)
    # if data:
    #     # this data has server added fields that need to be removed
    #     for row in data:
    #         row.pop('server_last_edit_date')
    # else:
    #     data = []
    # if data and cursor:
    #     return {"rules": data, "cursor": cursor}
    # else:
    #     return {'rules': data}


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
    sqlalchemy_util.read(collection, data, multiple)
    # if collection == 'rules':
    #     db.collection('machine_status').document('last_rule_delete').set({'date': datetime.now(timezone.utc)})
    # docs = list(get_doc_by_match(collection, data))
    # if len(docs) == 0:
    #     return 404, f'Data was not found in {collection} so could not be deleted.'
    # if len(docs) == 1:
    #     db.collection(collection).document(docs[0].id).delete()
    #     return 200, f'Match found and deleted from {collection}.'
    # if multiple:
    #     for doc in docs:
    #         db.collection(collection).document(doc.id).delete()
    #     return 200, f'Multiple matches found in {collection}, all deleted.'
    # else:
    #     return 400, f'Included data has more than one match in {collection}. Please check database and request manually.'


def get_last_rule_delete() -> datetime:
    # Gets the datetime the last delete action is stored, returns None if no deletion has ever occured
    sqlalchemy_util.get_last_rule_delete()
    # doc = get_doc_by_id('machine_status', 'last_rule_delete')
    # if doc.exists:
    #     return doc.to_dict()['date']
    # else:
    #     return None


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
    sqlalchemy_util.lookup_by_id(collection, row_id)

    # result = get_doc_by_id(collection, row_id)
    # if not result.exists:
    #     return None
    # return result.to_dict()


def lookup(collection: str, data: dict) -> list:
    '''
    Returns all rows in the collection matching the given data

    Parameters:
        collection: name of the collection to read from
        data: every key value pair in data should exist in all returned rows

    Returns:
        list: list of dicts, where every dict reflects one row in the database matching the given data
    '''
    sqlalchemy_util.lookup(collection, data)
    # result = list(get_doc_by_match(collection, data))
    # result = [doc.to_dict() for doc in result]
    # return result


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
    sqlalchemy_util.edit(collection, data, row_id)
    # doc = get_doc_by_id(collection, row_id)
    # if doc.exists:
    #     if collection == 'rules':
    #         data['server_last_edit_date'] = datetime.now(timezone.utc)
    #     db.collection(collection).document(row_id).set(data)
    #     return 200, f'Entry {row_id} edited in {collection}'
    # else:
    #     return 404, f"Data {row_id} not found in {collection}, so cannot be edited"


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
    sqlalchemy_util.add_or_edit(collection, data, row_id)
    # if collection == 'rules':
    #     data['server_last_edit_date'] = datetime.now(timezone.utc)
    # db.collection(collection).document(row_id).set(data)
    # return 200, f'Entry added to (or edited in) {collection}'

# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------

