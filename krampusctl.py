#!/usr/bin/env python3

import logging
import argparse
import os
import requests
import sys
import yaml

from santa_classes import KrampusHostConfig, KrampusRule

# ----------------------------------------
#          server requests
# ----------------------------------------
def server_req(url, data, accepted_errors=[], fail_on_errors=[]):
    for i in range(3):
        req_result = send_authenticated_request(url, data)
        result = req_result
        if req_result.status_code < 300:
            if not req_result.headers.get('content-type') == 'application/json':
                logging.debug(req_result.text)
            return req_result
        elif req_result.status_code in accepted_errors:
            logging.warning(req_result.text)
            logging.debug(data)
            return req_result
        elif req_result.status_code in fail_on_errors:
            logging.error(f'Error {req_result.status_code}. {req_result.text}')
            logging.debug(data)
            logging.error(f'Cannot continue.')
            sys.exit(1)
        else:
            logging.error(f'Error {req_result.status_code}. {req_result.text}')
            logging.debug(data)
    logging.error(f'Cannot continue.')
    sys.exit(1)

# ----------------------------------------
#              auth logic
# ----------------------------------------
def send_authenticated_request(url, data):
    if os.environ.get('CTL_SECRET'):
        return requests.post(url, json=data, headers={'Krampus-Auth': os.environ.get('CTL_SECRET')})
    elif os.environ.get('AUTH_HEADER_NAME') and os.environ.get('AUTH_HEADER_VALUE'):
        return requests.post(url, json=data, headers={os.environ.get('AUTH_HEADER_NAME'): os.environ.get('AUTH_HEADER_VALUE')})
    else:
        return requests.post(url, json=data)

# ----------------------------------------
#               DB logic
# ----------------------------------------
def replicate(data, server_url, limit):
    for collection in data:
        # read from db
        collection_data = data[collection]
        url = server_url + f'/db-read/{collection}'
        req_result = server_req(url, {'limit': limit})
        req_result = process_rep_response(req_result)
        while 'cursor' in req_result:
            # still reading
            # process data (note data that does not need to be added, delete what needs to be deleted)
            collection_data = process_replicate_chunk(req_result['data'], collection_data, collection, f'{server_url}/db-del/{collection}', f'{server_url}/db-edit-row/{collection}')
            # get new data
            req_result = server_req(url, {'limit': limit, 'cursor':req_result['cursor']})
            req_result = process_rep_response(req_result)
        # process last data chunk
        collection_data = process_replicate_chunk(req_result['data'], collection_data, collection, f'{server_url}/db-del/{collection}', f'{server_url}/db-edit-row/{collection}')
        # for collection add all missing data
        for d in collection_data:
            server_req(f'{server_url}/db-add/{collection}', d, fail_on_errors=[409])

def process_rep_response(req_res):
    # if request contains json
    if req_res.headers.get('content-type') == 'application/json':
        # get json
        req_res = req_res.json()
        # check if data has expected shape
        if 'data' in req_res:
            return req_res
    logging.error('Unexpected response from server. Cannot continue.')
    sys.exit(1)

def process_replicate_chunk(response_data, data, collection, del_url, edit_url):
    # print(f'processing chunk. response data size {len(response_data)}, data size {len(data)}')
    new_data = data.copy()
    for i, d in enumerate(data):
        match, is_full_match = check_dict_to_database(response_data, d)
        if match:
            #  old data does not need to be deleted
            response_data.remove(match)
            # new data does not need to be added
            new_data.remove(d)
            # new data may need to be edited
            if not is_full_match:
                #  not full match needs to be edited, not added
                server_req(edit_url, d, fail_on_errors=[404, 400])
    # old data with no matches needs to be deleted
    for d in response_data:
        server_req(del_url, d, fail_on_errors=[404, 400])
    return new_data

def check_dict_to_database(database, d):
    id_match = False
    if 'row_id' in d:
        # match counts as any row with the same id
        for data in database:
            if 'row_id' in data and data['row_id'] == d['row_id']:
                return data, is_dict_match(d, data)
    else:
        # match has to be a full match
        for data in database:
            if is_dict_match(d, data):
                return data, True
    return None, None

def is_dict_match(d1, d2):
    match = True
    for key in d1:
        if match and not(key in d2 and d2[key] == d1[key]):
            match = False
    for key in set(d2.keys()).difference(set(d1.keys())):
        if match and key != 'row_id' and (not (d2[key] == None)):
            match = False
    return match

def add(data, server_url):
    for collection in data:
        logging.debug(f'Adding to {collection}')
        for row in data[collection]:
            req_result = server_req(f'{server_url}/db-add/{collection}', row, fail_on_errors=[409])

def edit_row(data, server_url):
    for collection in data:
        logging.debug(f'Editing {collection}')
        for row in data[collection]:
            if 'row_id' not in row:
                logging.error(f'Can only edit rows with a known id. The following row in {collection} is missing an id:\n{row}')
                sys.exit(1)
            server_req(f'{server_url}/db-edit-row/{collection}', row, fail_on_errors=[404])

def edit_fields(data, server_url):
    for collection in data:
        logging.debug(f'Editing {collection}')
        for row in data[collection]:
            if 'row_id' not in row:
                logging.error(f'Can only edit rows with a known id. The following row in {collection} is missing an id:\n{row}')
                sys.exit(1)
            server_req(f'{server_url}/db-edit-fields/{collection}', row, fail_on_errors=[404])

def delete(data, server_url):
    for collection in data:
        for row in data[collection]:
            success = False
            req_result = server_req(f'{server_url}/db-del/{collection}', row, accepted_errors=[400, 404])

def delete_multiple(data, server_url):
    for collection in data:
        for row in data[collection]:
            success = False
            req_result = server_req(f'{server_url}/db-del/{collection}', row, accepted_errors=[404])

def check_hostconfigs(l):
    for row in l:
        KrampusHostConfig(**row)
        if 'targets' not in row:
            row['targets'] = ['all']
    
def check_rules(l):
    for row in l:
        KrampusRule(**row)
        if 'targets' not in row:
            row['targets'] = ['all']
        # # check for keys
        # rule_keys = set(rule.keys())
        # mandatory_keys = {'identifier', 'policy', 'rule_type',}
        # possible_keys = mandatory_keys.union({'custom_msg', 'custom_url', 'notification_app_name', 'cel_expr', 'row_id', 'targets', 'exemptions'})
        # if 'policy' in rule_keys and rule['policy'] == 'CEL':
        #     mandatory_keys.add('cel_expr')
        # # are all mandatory keys present?
        # if not rule_keys.issuperset(mandatory_keys):
        #     logging.error(f'Rule is missing mandatory key(s) {mandatory_keys.difference(rule_keys)}.')
        #     logging.error(f'Mandatory keys: {mandatory_keys}')
        #     logging.error(f'Rule: {rule}')
        #     sys.exit(1)
        # # are all present keys expected?
        # if not possible_keys.issuperset(rule_keys):
        #     logging.error(f'Rule has unknown key(s) {rule_keys.difference(possible_keys)}.')
        #     logging.error(f'Possible keys: {possible_keys}')
        #     logging.error(f'Rule: {rule}')
        #     sys.exit(1)

def write_yaml(yaml_file, server_url, limit):
    result = {}
    for collection in ['hostconfigs', 'rules']:
        collection_data = []
        url = server_url + f'/db-read/{collection}'
        req_result = server_req(url, {'limit': limit})
        req_result = process_rep_response(req_result)
        while 'cursor' in req_result:
            # still reading
            # process data (note data that does not need to be added, delete what needs to be deleted)
            collection_data += req_result['data']
            # get new data
            req_result = server_req(url, {'limit': limit, 'cursor':req_result['cursor']})
            req_result = process_rep_response(req_result)
        # process last data chunk
        collection_data += req_result['data']
        # collection done
        result[collection] = collection_data
    with open(yaml_file, 'w') as f:
        yaml.dump(result, f, default_flow_style=False)
        

# ----------------------------------------
#                 File reader
# ----------------------------------------
def read_input_file(path, check_santa_validtiy):
    check_path_exists(path)
    if path.endswith('.yaml') or path.endswith('.yml'):
        return process_yaml(path, check_santa_validtiy)
    else:
        logging.error(f'File {path} is not a type of file this script is able to process. Please provide a yaml file.')
        sys.exit(1)

def check_path_exists(path, should_exit=True):
    if os.path.exists(path):
        return True
    elif should_exit:
        logging.error(f'Path {path} dpes not exist.')
        sys.exit(1)
    else:
        logging.warning(f'Path {path} does not exist. Continueing without access')
        return False

# ----------------------------------------
#                 yaml
# ----------------------------------------
def process_yaml(file_path, check_santa_validtiy) -> dict:
    result = read_yaml(file_path)
    check_valid_yaml_dict(result, check_santa_validtiy)
    return result

def read_yaml(file_path) -> dict:
    if not os.access(file_path, os.R_OK):
        logging.error(f'No access to {file_path}')
        sys.exit(1)    
    with open(file_path, 'r') as file_yaml:
        try:
            result = dict()
            data = yaml.safe_load_all(file_yaml)
            for d in data:
                result.update(d)
            return result
        except yaml.YAMLError as e:
            logging.error(f'Unable to load {file_path}')
            logging.error(e, exc_info=True)
            sys.exit(1)

def check_valid_yaml_dict(data, check_santa_validtiy):
    if type(data) != dict:
        logging.error(f'yaml data must be in the form of a dictionary with the top level key being the collection name. This data is of type {type(data)}.')
        sys.exit(1)
    for collection in data:
        collection_data = data[collection]
        if collection == 'rules': 
            if check_santa_validtiy:
                check_rules(collection_data)
        elif collection == 'hostconfigs':
            if check_santa_validtiy:
                check_hostconfigs(collection_data)
        else:
            logging.error(f'Only "rules" and "hostconfigs" are valid collections. The top level key {collection} is not recognised.')
            sys.exit(1)
        if type(collection_data) != list:
            logging.error(f'In the yaml for each collection, the value must be a list of rules or configurations. Instead the value has type {type(collection_data)}.')
            sys.exit(1)
        for el in collection_data:
            if type(el) != dict:
                logging.error(f'In the yaml for each collection, the value must be a list of rules or configurations, which must have type dict. Instead the elements of {collection}s have type {type(el)}.')
                sys.exit(1)

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

# ----------------------------------------
#                 Options
# ----------------------------------------
def process_args():
    parser = argparse.ArgumentParser(
		description='krampusctl is a command-line tool for applying configuration to a krampus server.',
		usage='%(prog)s [options]'
	)
    parser.add_argument('--apply', '-a', dest='rep_path',
                        help='copy this data to the database')
    parser.add_argument('--add', dest='add_path',
                        help='add this data to the database, without creating duplicates')
    parser.add_argument('--edit_row', dest='edit_row_path',
                        help='fully replace the data in the database at a specific id, with the assumption that it exists')
    parser.add_argument('--edit_fields', dest='edit_fields_path',
                        help='edits specifid fields in the data in the database at a specific row id, with the assumption that it exists')
    parser.add_argument('--delete', '-d', dest='del_path',
                        help='removes matches for the given data from the database, with the assumption that exactly one match will be found.')
    parser.add_argument('--delete_multiple', dest='del_path_m',
                           help='removes all matches for the given data from the database, with the assumption that at least one match will be found.')
    parser.add_argument('--limit', '-l', dest='limit', default=50,
                        help='limit for reading from database', type=int)
    parser.add_argument('--output_yaml', '-o', dest='output',
                        help='path where a yaml file will be written to reflect the current rules and hostconfigs in krampus.')
    parser.add_argument('--server', '-s', dest='server_url', default="http://0.0.0.0:8000",
                        help='krampus url')
    args = parser.parse_args()
    return args.rep_path, args.add_path, args.edit_row_path, args.edit_fields_path, args.del_path, args.del_path_m, args.limit, args.server_url, args.output

# ----------------------------------------
#                 Main
# ----------------------------------------
def main():
    setup_logging()
    rep_path, add_path, edit_row_path, edit_fields_path, del_path, del_path_m, limit, server_url, output = process_args()

    if [rep_path, add_path, edit_row_path, edit_fields_path, del_path, del_path_m].count(None) < 4:
        logging.error(f'Please only use one argument that edits the krampus database.')
        sys.exit(1)

    if rep_path:
        data = read_input_file(rep_path, True)
        replicate(data, server_url, limit)
    if add_path:
        data = read_input_file(add_path, True)
        add(data, server_url)
    if edit_row_path:
        data = read_input_file(edit_row_path, True)
        edit_row(data, server_url)
    if edit_fields_path:
        data = read_input_file(edit_fields_path, False)
        edit_fields(data, server_url)
    if del_path:
        data = read_input_file(del_path, False)
        delete(data, server_url)
    if del_path_m:
        data = read_input_file(del_path_m, False)
        delete_multiple(data, server_url)
    if output:
        write_yaml(output, server_url, limit)

if __name__ == '__main__':
    main()