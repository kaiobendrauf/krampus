#!/usr/bin/env python3

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import random
import signal
import sys

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
    if collection == 'rules':
        matches = db.lookup(collection, data)
        if len(matches) == 0:
            # new entry
            data['server_last_edit_date'] = datetime.now(timezone.utc)
        else:
            # old entry
            return 200, f'Data already found in {collection}, so was not added.'
        data['server_last_edit_date'] = datetime.now(timezone.utc)
    return db.add(collection, data)

# ----------------------------------------
#            Event Handler
# ----------------------------------------
def setup_event_handler():
    global event_handler
    setup_data = None
    if os.environ.get('PUB_SUB_EVENT_ID'):
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
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        result = process_preflight(machine_id, data)
        return result
    else:
        flask.abort(415)

@server.route('/eventupload/<machine_id>', methods=['POST'])
def eventupload(machine_id):
    logging.debug('eventupload')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        if 'events' in data:
            result = event_handler.send_events(data['events'])
            if result:
                return result
            return flask.Response(status=200)
        else:
            flask.abort(400) 
    else:
        flask.abort(415)

@server.route('/ruledownload/<machine_id>', methods=['POST'])
def ruledownload(machine_id):
    logging.debug('ruledownload')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        return flask.Response(status=200)
    else:
        flask.abort(415)

@server.route('/postflight/<machine_id>', methods=['POST'])
def postflight(machine_id):
    logging.debug('postflight')
    if flask.request.content_type == 'application/json':
        data = flask.request.get_json()
        return flask.Response(status=200)
    else:
        flask.abort(415)

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
            if result:
                if collection == 'rules':
                    # this data has server added fields that need to be removed
                    for row in result['data']:
                        row.pop('server_last_edit_date')
                return result
            else:
                return flask.Response(f'No items to read.', status=200)
        else:
            flask.abort(400)
    else:
        flask.abort(415)

# ----------------------------------------
#           SANTA Request Logic
# ----------------------------------------

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
    machine_status['stage'] = 'preflight'
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
    if new or request['request_clean_sync'] or (datetime.now(timezone.utc) > machine_status['full_sync_by']):
        machine_status['sync_type'] = 'CLEAN'
        hostconfig['sync_type'] = 'CLEAN'
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
        machine_status['full_sync_by'] = datetime.now(timezone.utc) + timedelta(days=random.randint(min_days, max_days))
    elif 'sync_type' in hostconfig:
        machine_status['sync_type'] = hostconfig['sync_type']


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
#                 Options
# ----------------------------------------

def process_options():
    pass
    # parser = optparse.OptionParser()
    # parser.set_usage('Usage: %prog [options]')
    # parser.add_option('--baseline-path', '-b', dest='baseline_path',
    #                     help='Optional path to custom baseline yaml file.')
    # parser.add_option('--baseline-name', '-n', dest='baseline_name',
    #                     help='Optional name of baseline yaml file.')
    # parser.add_option('--custom', '-c', dest='custom',
    #                     help='Optional path to custom folder.')
    # parser.add_option('--rules', '-r', dest='rules',
    #                     help='Optional path to rules folder.')
    # parser.add_option('--folder', '-f', dest='folder',
    #                     help='Optional path to a folder optionally containing a baselines, custom and rules folder. These folders will be used if paths are not directly specified.')
    # parser.add_option('--config', '-y', dest='config_file',
    #                     help=f'Optional path to the configuration yaml file, which specifies values for the munki item. Defaults to {CONFIG_PATH}')
    # parser.add_option('--munki', '-m', dest='output_path', default=OUTPUT_PATH,
    #                     help=f'Optional path to the directory generated munki files should be written to. Defaults to {OUTPUT_PATH}')
    # parser.add_option('--prefix', dest='prefix',
    #                     help=f'Optional prefix to add to the name of every generated munki item and it\'s file name.')
    # parser.add_option('--suffix', dest='suffix',
    #                     help=f'Optional suffix to add to the name of every generated munki item and it\'s file name..')
    # parser.add_option('--version', '-v', dest='version',
    #                     help=f'Optional version to be set in every munki item and appended to the name of every generated munki item. Specifying a version here will override a version given in the configuration yaml file.')
    # parser.add_option('--separate', '-s', dest='separate_fix', action='store_true',
    #                     help='Write fix script in preinstall_script, rather than in installcheck_script.')
    # parser.add_option('--no-munki-output', dest='no_echo', action='store_true',
    #                     help='Write fix script in preinstall_script, rather than in installcheck_script.')
    # parser.add_option('--config-profile-list-file', dest='config_profile_list_file',
    #                     help='Optional path to the file where munki items will write to if their fix can only be implemented by a configuration profile. Specifying a file path here will override a file given in the configuration yaml file.')
    # parser.add_option('--markdown', dest='markdown_path', default=MD_PATH,
    #                     help=f'Optional file name to print markdown summary of how the rules were processed by this script. Defaults to {MD_PATH}')
    # options, _ = parser.parse_args()
    # return options.baseline_path, options.baseline_name, options.custom, options.rules, options.folder, options.config_file, options.output_path, options.prefix, options.suffix, options.version, options.separate_fix, not options.no_echo, options.config_profile_list_file, options.markdown_path

# ----------------------------------------
#                 Main
# ----------------------------------------

def main():
    setup_logging()
    setup_db()
    setup_event_handler()

    # Use waitress to run flask
    serve(server, host='0.0.0.0', port=3000)
    

if __name__ == '__main__':
    main()