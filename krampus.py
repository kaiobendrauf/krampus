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


# Set up request listener
server = flask.Flask(__name__)

# ----------------------------------------
#               Database
# ----------------------------------------
def setup_db():
    global db
    if os.environ.get('GCP_PROJ_ID'):
        # firestore database
        import dbs.db_firestore as db
    else:
        logging.error('No valid db type given, unable to continue.')
        sys.exit(1)
    db.setup()

def add_to_db(collection, data):
    if collection == 'hostconfigs':
        if 'target' in data:
            target = data['target']
        else:
            target = 'all'
        if db.lookup_by_id(collection, target):
            return 409, f'Hostconfig with target {target} already exists.'
        else:
            return db.add(collection, data, target)
    return db.add(collection, data)

# ----------------------------------------
#            Event Handler
# ----------------------------------------
def setup_event_handler():
    global event_handler
    setup_data = None
    # print(os.environ)
    if os.environ.get('PUB_SUB_TOPIC_ID'):
        # pub sub event handler
        logging.info("Using Pub/Sub as the event handler.")
        import event_handlers.event_handler_pubsub as event_handler
    elif os.environ.get('KRAMPUS_EVENT_HANDLER_FULL'):
        # full events published to krampus' database
        logging.info("Using Krampus' database as the event handler, to store full events.")
        import event_handlers.event_handler_krampus_full as event_handler
        setup_data = db
    elif os.environ.get('KRAMPUS_EVENT_HANDLER_SUMMARY'):
        # summaries of events published to krampus' database
        logging.info("Using Krampus' database as the event handler, to store summarised events.")
        import event_handlers.event_handler_krampus_summary as event_handler
        setup_data = db
    else:
        # no event handler
        logging.warning(f'No event handler found. Events will not be processed.')
        import event_handlers.event_handler_empty as event_handler

    if setup_data:
        event_handler.setup(setup_data)
    else:
        event_handler.setup()

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
    logging.debug('preflight')
    print(flask.request.headers)
    print(flask.request.get_data())
    print(zlib.decompress(flask.request.get_data()))
    data = get_request_data(flask.request)
    
    result = process_preflight(machine_id, data)
    return result
    
@server.route('/eventupload/<machine_id>', methods=['POST'])
def eventupload(machine_id):
    logging.debug('eventupload')
    data = get_request_data(flask.request)
    if 'events' in data:
        result = event_handler.send_events(data['events'])
        if result:
            return result
        return flask.Response(status=200)
    else:
        flask.abort(400) 

@server.route('/ruledownload/<machine_id>', methods=['POST'])
def ruledownload(machine_id):
    logging.debug('ruledownload')
    data = get_request_data(flask.request)
    machine_status = db.lookup_by_id('machinestatus', machine_id)
    if machine_status:
        return process_ruledownload(machine_id, machine_status, data)
    else:
        flask.abort(404)

@server.route('/postflight/<machine_id>', methods=['POST'])
def postflight(machine_id):
    logging.debug('postflight')
    data = get_request_data(flask.request)
    machine_status = db.lookup_by_id('machinestatus', machine_id)
    if machine_status:
        process_postflight(machine_id, machine_status, data)
        return flask.Response(status=200)
    else:
        flask.abort(404)

# ----------------------------------------
#          Listeners - ctl
# ----------------------------------------

@server.route('/db-add/<collection>', methods=['POST'])
def db_add(collection):
    logging.debug('add request')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        status_code, text = add_to_db(collection, data)
        return flask.Response(text, status=status_code)
    else:
        flask.abort(415)

@server.route('/db-del/<collection>', methods=['POST'])
def db_del(collection):
    logging.debug('del request')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        status_code, text = db.delete(collection, data)
        return flask.Response(text, status=status_code)
    else:
        flask.abort(415)

@server.route('/db-del-multiple/<collection>', methods=['POST'])
def db_del_multiple(collection):
    logging.debug('del request')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        status_code, text = db.delete(collection, data, True)
        return flask.Response(text, status=status_code)
    else:
        flask.abort(415)

@server.route('/db-read/<collection>', methods=['POST'])
def db_read(collection):
    logging.debug('read request')
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

# ----------------------------------------
#           SANTA Request Logic
# ----------------------------------------

def get_request_data(request):
    if request.content_type == 'application/json':
        if request.headers.get('Content-Encoding') == "deflate":
            decompressed_data = zlib.decompress(request.get_data())
            data = json.loads(decompressed_data.decode('utf-8'))
        else:
            data = request.get_json()
        return data
    else:
        flask.abort(415)

def decompress_data(data):
    decompressed_data = zlib.decompress(data)
    return json.loads(decompressed_data.decode('utf-8'))

def process_preflight(machine_id, data):
    hostconfig = get_hostconfig(machine_id, data)
    # machine_status = data to be stored for other requests
    machine_status = db.lookup_by_id('machinestatus', machine_id)
    new = False
    if not machine_status:
        machine_status = dict()
        choose_sync_type(data, machine_status, hostconfig, True)
        new = True
    else:
        choose_sync_type(data, machine_status, hostconfig)
    # machine_status['stage'] = 'preflight'
    machine_status['n_rules_sent'] = 0
    if new:
        db.add('machinestatus', machine_status, machine_id)
    else:
        db.edit('machinestatus', machine_status, machine_id)
    return hostconfig

def get_hostconfig(machine_id, data):
    result = dict()
    groups = []
    if 'primary_user_groups' in data:
        groups = data['primary_user_groups']
    l = db.read('hostconfigs', 2)
    if l:
        if len(l['data']) == 1:
            result = l['data'][0]
        # more than one result so need to find the right one
        elif len(l['data']) == 2:
            # is there a specific config just for that machine?
            machine_config = db.lookup_by_id('hostconfigs', machine_id)
            # no specific config for that machine -> look at group
            if machine_config:
                result = machine_config
            else:
                group_configs = []
                for group in groups:
                    group_config = db.lookup_by_id('hostconfigs', group)
                    if group_config:
                        group_configs += [group_config]
                # no individual or group config -> look for global config
                if len(group_configs) == 1:
                    result = group_configs[0]
                else:
                    result = db.lookup_by_id('hostconfigs', 'all')
    return result

def choose_sync_type(request, machine_status, hostconfig, new=False):
    if new or request.get('request_clean_sync') or (datetime.now(timezone.utc) > machine_status['clean_sync_by']):
        if hostconfig and type(hostconfig) == dict and 'sync_type' in hostconfig and hostconfig['sync_type'] == 'CLEAN_ALL':
            machine_status['sync_type'] = 'CLEAN_ALL'
            hostconfig['sync_type'] = 'CLEAN_ALL'
        else:
            machine_status['sync_type'] = 'CLEAN'
            hostconfig['sync_type'] = 'CLEAN'
        # clean sync will now be required until completed
        machine_status['clean_sync_by'] = datetime.now(timezone.utc)
    elif 'sync_type' in hostconfig:
        machine_status['sync_type'] = hostconfig['sync_type']
    else:
        machine_status['sync_type'] = 'NORMAL'

def pick_future_clean_sync_by(machine_status):
    min_days = os.environ.get('MIN_CLEAN_ALL_DAYS')
    if not min_days:
        min_days = 7
    else:
        min_days = int(min_days)
    max_days = os.environ.get('MAX_CLEAN_ALL_DAYS')
    if not max_days:
        min_days = 13
    else:
        max_days = int(max_days)
    machine_status['clean_sync_by'] = datetime.now(timezone.utc) + timedelta(days=random.randint(min_days, max_days))

def process_ruledownload(machine_id, machine_status, data):
    batch_size = os.environ.get('BATCH_SIZE')
    if not batch_size:
        batch_size = 50
    else:
        batch_size = int(batch_size)
    cursor = None
    if 'cursor' in data:
        cursor = data['cursor']
    if machine_status['sync_type'] == 'CLEAN' or machine_status['sync_type'] == 'CLEAN_ALL' or ('last_check_in' not in machine_status):
        result = db.read('rules', batch_size, cursor)
        result['rules'] = result['data']
        del result['data']
    else:
        result = db.read_new_rules(machine_status['last_check_in'], batch_size, cursor) 
    machine_status['n_rules_sent'] += len(result['rules'])
    db.edit('machinestatus', machine_status, machine_id)
    return result


def process_postflight(machine_id, machine_status, data):
    if data['rules_received'] == machine_status['n_rules_sent']:
        # data sent successfully
        if data['rules_processed'] == data['rules_received']:
            # data processed successfully, these rules do not need to be resent
            machine_status['last_check_in'] = datetime.now(timezone.utc)
        else:
            logging.warning(f'{data["rules_received"]} rules received by {machine_id}, but {data["rules_processed"]} processed.')
    else:
        logging.warning(f'{machine_status["n_rules_sent"]} rules sent to {machine_id}, but {data["rules_received"]} received.')
    if data['sync_type'] == 'CLEAN' or data['sync_type'] == 'CLEAN_ALL':
        pick_future_clean_sync_by(machine_status)
        logging.debug('Updating clean_sync_by date for {machine_id}.')
    machine_status['n_rules_sent'] = 0
    db.edit('machinestatus', machine_status, machine_id)


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
    setup_event_handler()

    if not os.environ.get('BATCH_SIZE'):
        logging.warning(f'No batch size defined, using default: 50.')


    # Use waitress to run flask
    serve(server, host='0.0.0.0', port=8000)
    

if __name__ == '__main__':
    main()