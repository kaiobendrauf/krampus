#!/usr/bin/env python3

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import random
import signal
import sys
import zlib

import flask
from waitress import serve

from santa_classes import KrampusHostConfig, KrampusRule


# Set up request listener
server = flask.Flask(__name__)

# ----------------------------------------
#            Authentication
# ----------------------------------------
def setup_auth():
    setup_sync_auth()
    setup_ctl_auth()

def setup_sync_auth():
    global auth_sync
    setup_data = None
    if os.environ.get('SYNC_SECRET'):
        # header auth
        import auths.auth_header as auth_sync
        setup_data = os.environ.get('SYNC_SECRET')
    else:
        logging.info('No valid authentication for syncs defined.')
        import auths.auth_empty as auth_sync
    auth_sync.setup(False, setup_data)

def setup_ctl_auth():
    global auth_ctl
    setup_data = None
    if os.environ.get('CTL_SECRET'):
        # header auth
        import auths.auth_header as auth_ctl
        setup_data = os.environ.get('CTL_SECRET')
    else:
        logging.warning('No valid authentication for krampusctl defined. Make sure you are authenticating elsewhere.')
        import auths.auth_empty as auth_ctl
    auth_ctl.setup(True, setup_data)


# ----------------------------------------
#               Database
# ----------------------------------------
def setup_db():
    global db
    if os.environ.get('GCP_PROJ_ID'):
        # firestore database
        import dbs.db_firestore as db
    elif os.environ.get('MYSQL_HOST'):
        # mysql database
        import dbs.db_mysql as db
    elif os.environ.get('POSTGRES_HOST'):
        # postgres database
        import dbs.db_psql as db
    else:
        logging.error('No valid db type given, unable to continue.')
        sys.exit(1)
    db.setup()

def validate_data(collection, data):
    if collection == 'rules':
        KrampusRule(**data)
    if collection == 'hostconfigs':
        KrampusHostConfig(**data)

# ----------------------------------------
#            Event Handler
# ----------------------------------------
def setup_event_handler():
    global event_handler
    setup_data = None
    if os.environ.get('PUB_SUB_TOPIC_ID'):
        # pub sub event handler
        logging.info("Using Pub/Sub as the event handler.")
        import event_handlers.event_handler_pubsub as event_handler
    else:
        # no event handler
        logging.warning(f'No event handler found. Events will not be processed.')
        import event_handlers.event_handler_empty as event_handler

    event_handler.setup(setup_data)

# ----------------------------------------
#          Listeners - Generic
# ----------------------------------------
@server.after_request
def webserver_logging(response):
    logging.debug(response)
    return response

@server.route('/')
def index():
    # Not a request with a predefined response
    return '<h1>Krampus</h1>'

# ----------------------------------------
#          Listeners - SANTA
# ----------------------------------------

@server.route('/preflight/<machine_id>', methods=['POST'])
def preflight(machine_id):
    logging.debug(f'preflight for {machine_id}')
    if auth_sync.auth_sync(flask.request, machine_id):
        data = get_request_data(flask.request)
        result = process_preflight(machine_id, data)
        # logging.debug(f'preflight result:\n{result}')
        return result
    else:
        logging.warning(f'Attempted sync request (preflight) from {machine_id} failed because authentication failed.')
        flask.abort(403)
    
@server.route('/eventupload/<machine_id>', methods=['POST'])
def eventupload(machine_id):
    logging.debug(f'eventupload for {machine_id}')
    if auth_sync.auth_sync(flask.request, machine_id):
        data = get_request_data(flask.request)
        if 'events' in data:
            result = event_handler.send_events(data['events'])
            if result:
                return result
            return flask.Response(status=200)
        else:
            flask.abort(400) 
    else:
        logging.warning(f'Attempted sync request (eventupload) from {machine_id} failed because authentication failed.')
        flask.abort(403)

@server.route('/ruledownload/<machine_id>', methods=['POST'])
def ruledownload(machine_id):
    logging.debug(f'ruledownload for {machine_id}')
    if auth_sync.auth_sync(flask.request, machine_id):
        data = get_request_data(flask.request)
        machine_status = get_machine_status(machine_id)
        if machine_status:
            result = process_ruledownload(machine_id, machine_status, data)
            # logging.debug(f'ruledownload result:\n{result}')
            return result
        else:
            logging.warning(f'Attempted sync request (ruledownload) from {machine_id} failed because machine status for sync could not be found.')
            flask.abort(404)
    else:
        logging.warning(f'Attempted sync request (ruledownload) from {machine_id} failed because authentication failed.')
        flask.abort(403)

@server.route('/postflight/<machine_id>', methods=['POST'])
def postflight(machine_id):
    logging.debug(f'postflight for {machine_id}')
    if auth_sync.auth_sync(flask.request, machine_id):
        data = get_request_data(flask.request)
        machine_status = get_machine_status(machine_id)
        if machine_status:
            process_postflight(machine_id, machine_status, data)
            return flask.Response(status=200)
        else:
            logging.warning(f'Attempted sync request (postflight) from {machine_id} failed because machine status for sync could not be found.')
            flask.abort(404)
    else:
        logging.warning(f'Attempted sync request (postflight) from {machine_id} failed because authentication failed.')
        flask.abort(403)

# ----------------------------------------
#          Listeners - ctl
# ----------------------------------------

@server.route('/db-add/<collection>', methods=['POST'])
def db_add(collection):
    logging.debug(f'add request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            validate_data(collection, data)
            status_code, text = db.add(collection, data)
            return flask.Response(text, status=status_code)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-add request failed because authentication failed.')
        flask.abort(403)

# @server.route('/db-add-edit/<collection>', methods=['POST'])
# def db_add_or_edit(collection):
#     logging.debug(f'add/edit request for {collection}')
#     if auth_ctl.auth_ctl(flask.request):
#         if flask.request.content_type == 'application/json':
#             data = flask.request.get_json()
#             status_code, text = add_edit_db(collection, data)
#             return flask.Response(text, status=status_code)
#         else:
#             flask.abort(415)
#     else:
#         logging.warning(f'Attempted db-add-edit request failed because authentication failed.')
#         flask.abort(403)

@server.route('/db-del/<collection>', methods=['POST'])
def db_del(collection):
    logging.debug(f'del request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            status_code, text = db.delete(collection, data)
            return flask.Response(text, status=status_code)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-del request failed because authentication failed.')
        flask.abort(403)

@server.route('/db-del-multiple/<collection>', methods=['POST'])
def db_del_multiple(collection):
    logging.debug(f'del mult request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            status_code, text = db.delete(collection, data, True)
            return flask.Response(text, status=status_code)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-del-multiple request failed because authentication failed.')
        flask.abort(403)

@server.route('/db-edit-row/<collection>', methods=['POST'])
def db_edit_row(collection):
    logging.debug(f'edit request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            validate_data(collection, data)
            status_code, text = db.edit_row(collection, data)
            return flask.Response(text, status=status_code)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-edit request failed because authentication failed.')
        flask.abort(403)

@server.route('/db-edit-fields/<collection>', methods=['POST'])
def db_edit_fields(collection):
    logging.debug(f'edit request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            status_code, text = db.edit_fields(collection, data)
            return flask.Response(text, status=status_code)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-edit request failed because authentication failed.')
        flask.abort(403)

@server.route('/db-read/<collection>', methods=['POST'])
def db_read(collection):
    logging.debug(f'read request for {collection}')
    if auth_ctl.auth_ctl(flask.request):
        if flask.request.content_type == 'application/json':
            data = flask.request.get_json()
            if 'limit' in data:
                if 'cursor' in data:
                    result = db.read(collection, data['limit'], data['cursor'])
                else:
                    result = db.read(collection, data['limit'])
                return result
            else:
                flask.abort(400)
        else:
            flask.abort(415)
    else:
        logging.warning(f'Attempted db-read request failed because authentication failed.')
        flask.abort(403)


# @server.route('/db-get/<collection>/<i>', methods=['POST'])
# def db_read(collection):
#     logging.debug(f'get request for row {i} in {collection}')
#     if auth_ctl.auth_ctl(flask.request):
#         data = db.lookup_by_id(collection, i)
#         if data:
#             return data
#         else:
#             flask.abort(404)
#     else:
#         logging.warning(f'Attempted db-read request failed because authentication failed.')
#         flask.abort(403)



# ----------------------------------------
#           SANTA Request Logic
# ----------------------------------------

# data processing
# ---------------
def get_request_data(request):
    if request.content_type == 'application/json':
        if request.headers.get('Content-Encoding') == "deflate":
            decompressed_data = zlib.decompress(request.get_data())
            data = json.loads(decompressed_data.decode('utf-8'))
        else:
            data = request.get_json()
        # logging.debug(f'request data:\n{data}')
        return data
    else:
        flask.abort(415)

def decompress_data(data):
    decompressed_data = zlib.decompress(data)
    return json.loads(decompressed_data.decode('utf-8'))

# preflight
# ---------
def process_preflight(machine_id, data):
    hostconfig = get_hostconfig(machine_id, data)
    # machine_status = data to be stored for other requests
    machine_status = get_machine_status(machine_id)
    new = False
    if machine_status is None:
        machine_status = {'machine_id': machine_id}
        new = True
    choose_sync_type(data, machine_status, hostconfig, new)
    # machine_status['stage'] = 'preflight'
    if 'primary_user_groups' in data:
        machine_status['primary_user_groups'] = data['primary_user_groups']
    else:
        machine_status.pop('primary_user_groups', None)
    if 'primary_user' in data:
        machine_status['primary_user'] = data['primary_user']
    else:
        machine_status.pop('primary_user', None)
    machine_status['n_rules_sent'] = 0
    if new:
        db.add('machinestatus', machine_status)
    else:
        db.edit_row('machinestatus', machine_status)
    return hostconfig

def get_machine_status(machine_id):
    results = db.lookup('machinestatus', {'machine_id': machine_id})
    if len(results) == 0:
        return None
    elif len(results) == 1:
        return results[0]
    else:
        logging.warning(f'{len(results)} machine status entries for machine {machine_id}. Keeping {results[0]['row_id']}')
        for result in results[1:]:
            db.delete('machinestatus', result)
        return results[0]

def get_hostconfig(machine_id, data):
    # lookup hostconfigs for machine_id
    l = [(machine_id, 'machine_id')]
    for k in ['primary_user', 'primary_user_groups']:
        if k in data:
            l.append((data[k], k))
    l.append(('all', 'all machines'))
    for target, s in l:
        result = hostconfig_check_target(target, machine_id, data, s)
        if result is not None:
            return result
    return dict()

def hostconfig_remove_krampus_data_hostconfig(hostconfig):
    hostconfig.pop('row_id', None)
    hostconfig.pop('targets', None)
    hostconfig.pop('exclusions', None)
    return hostconfig

def hostconfig_check_target(target, machine_id, machine_data, s):
    results = []
    result_ids = set()
    if isinstance(target, list):
        for el in target:
            hostconfigs = db.lookup_hostconfig_by_target(el)
            for hostconfig in hostconfigs:
                if not is_target_excluded(hostconfig, machine_id, machine_data):
                    results.append(hostconfig)
                    result_ids.add(hostconfig['row_id'])
    else:
        hostconfigs = db.lookup_hostconfig_by_target(target)
        for hostconfig in hostconfigs:
            if not is_target_excluded(hostconfig, machine_id, machine_data):
                results.append(hostconfig)
                result_ids.add(hostconfig['row_id'])
    if len(result_ids) == 1:
        return hostconfig_remove_krampus_data_hostconfig(results[0])
    if len(result_ids) > 1:
        logging.warning(f'Conflicting hostconfigs found for {machine_id}, when looking at hostconfigs that target {s}. Hostconfigs with the following ids apply: {result_ids}')
        return hostconfig_remove_krampus_data_hostconfig(results[0])

def is_target_excluded(db_data, machine_id, machine_data):
    if 'exclusions' in db_data:
        if machine_id in db_data['exclusions']:
            return True 
        if 'primary_user' in machine_data:
            if machine_data['primary_user'] in db_data['exclusions']:
                return True
        if 'primary_user_groups' in machine_data:
            for group in machine_data['primary_user_groups']:
                if group in db_data['exclusions']:
                    return True
    return False

def choose_sync_type(request, machine_status, hostconfig, new=False):
    if new or request.get('request_clean_sync') or (datetime.now(timezone.utc) > machine_status['clean_sync_by']) or (not has_clean_sync_since_delete(machine_status)):
        if hostconfig and type(hostconfig) == dict and 'sync_type' in hostconfig and hostconfig['sync_type'].lower() == 'clean_all':
            machine_status['sync_type'] = 'CLEAN_ALL'
            hostconfig['sync_type'] = 'CLEAN_ALL'
        else:
            machine_status['sync_type'] = 'CLEAN'
            hostconfig['sync_type'] = 'CLEAN'
        # clean sync will now be required until completed
        machine_status['clean_sync_by'] = datetime.now(timezone.utc)
    elif hostconfig and type(hostconfig) == dict and 'sync_type' in hostconfig:
        machine_status['sync_type'] = hostconfig['sync_type']
    else:
        machine_status['sync_type'] = 'NORMAL'

def has_clean_sync_since_delete(machine_status):
    last_rule_delete = db.get_last_rule_delete()
    if not last_rule_delete:
        # a rule has never been deleted
        return True
    if 'last_clean_sync' in machine_status:
        last_clean_sync = machine_status['last_clean_sync']
        return last_clean_sync > last_rule_delete
    else:
        # never completed a clean sync
        return False

def pick_future_clean_sync_by(machine_status):
    min_days = os.environ.get('MIN_CLEAN_SYNC_DAYS')
    if not min_days:
        min_days = 7
    else:
        min_days = int(min_days)
    max_days = os.environ.get('MAX_CLEAN_SYNC_DAYS')
    if not max_days:
        max_days = 13
    else:
        max_days = int(max_days)
    machine_status['clean_sync_by'] = datetime.now(timezone.utc) + timedelta(days=random.randint(min_days, max_days))

# rule download
# -------------
def process_ruledownload(machine_id, machine_status, data):
    batch_size = os.environ.get('BATCH_SIZE')
    if not batch_size:
        batch_size = 50
    else:
        batch_size = int(batch_size)
    cursor = None
    if 'cursor' in data:
        cursor = data['cursor']
    if machine_status['sync_type'].lower() == 'clean' or machine_status['sync_type'].lower() == 'clean_all' or ('last_check_in' not in machine_status):
        logging.debug(f'Performing Clean sync for {machine_id}')
        result = db.read('rules', batch_size, cursor)
    else:
        result = db.read_new_rules(machine_status['last_check_in'], batch_size, cursor) 

    rules = []
    for rule in result['data']:
        targets = rule.pop('targets', None)
        exclusions = rule.pop('exclusions', None)
        if check_if_targets_machine(targets, machine_id, machine_status) and (not check_if_targets_machine(exclusions, machine_id, machine_status)):
            rule.pop('row_id', None)
            rules.append(rule)
    result['rules'] = rules
    result.pop('data')

    machine_status['n_rules_sent'] += len(result['rules'])
    db.edit_row('machinestatus', machine_status)
    return result

def check_if_targets_machine(targets, machine_id, machine_status):
    if targets:
        if 'all' in targets or machine_id in targets:
            return True
        if 'primary_user' in machine_status:
            if machine_status['primary_user'] in targets:
                return True
        if 'primary_user_groups' in machine_status:
            for group in machine_status['primary_user_groups']:
                if group in targets:
                    return True

# postflight
# ----------
def process_postflight(machine_id, machine_status, data):
    if machine_status['n_rules_sent'] > 0:
        # check if rules received
        if 'rules_received' in data:
            if data['rules_received'] == machine_status['n_rules_sent']:
                if 'rules_processed' in data:
                    if data['rules_processed'] == data['rules_received']:
                        # successful sync
                        machine_status['last_check_in'] = datetime.now(timezone.utc)
                        process_postflight_sync_type(machine_id, machine_status, data)
                    else:
                        logging.warning(f'{data["rules_received"]} rules received by {machine_id}, but {data["rules_processed"]} processed.')
                else:
                    logging.warning(f'no rules reported as processed by {machine_id}, but {machine_status["n_rules_sent"]} sent.')
            else:
                logging.warning(f'{machine_status["n_rules_sent"]} rules sent to {machine_id}, but {data["rules_received"]} received.')
        else:
            logging.warning(f'no rules reported as received by {machine_id}, but {machine_status["n_rules_sent"]} sent.')
    else:
        # successful sync
        machine_status['last_check_in'] = datetime.now(timezone.utc)
        process_postflight_sync_type(machine_id, machine_status, data)
    machine_status['n_rules_sent'] = 0
    db.edit_fields('machinestatus', machine_status)

def process_postflight_sync_type(machine_id, machine_status, data):
    if 'syncType' in data and (data['syncType'].lower() == 'clean' or data['syncType'].lower() == 'clean_all'):
        logging.debug(f'Clean sync for {machine_id} succesfull.')
        pick_future_clean_sync_by(machine_status)
        logging.debug(f'Updating clean_sync_by date for {machine_id} to {datetime.now(timezone.utc)}.')
        machine_status['last_clean_sync'] = datetime.now(timezone.utc)

# ----------------------------------------
#          Request Verification
# ----------------------------------------

# ----------------------------------------
#                 Logging
# ----------------------------------------
def setup_logging():
    # read logging level from env
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s (%(module)s): %(message)s',
        datefmt='%d/%m/%Y %H:%M:%S',
        stream=sys.stdout)
    setup_signal_logging()

def setup_signal_logging():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def signal_handler(signum, _):
    logging.info(f'Received signal {signum}, shutting down gracefully...')
    sys.exit(0)

def request_logging():
    s = ''
    logging.info(s)


# ----------------------------------------
#                 Main
# ----------------------------------------
def main():
    setup_logging()
    setup_db()
    setup_auth()
    setup_event_handler()

    if not os.environ.get('BATCH_SIZE'):
        logging.warning(f'No batch size defined, using default: 50.')


    # Use waitress to run flask
    serve(server, host='0.0.0.0', port=8000)
    

if __name__ == '__main__':
    main()