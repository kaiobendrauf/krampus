#!/usr/bin/env python3

import argparse
import json
import logging
import os
import requests
import sys
import yaml

from santa_classes import KrampusHostConfig, KrampusRule

# ----------------------------------------
#          server requests
# ----------------------------------------
def server_req(url, data, accepted_errors=[], fail_on_errors=[], debug_print=True, add_auth=True):
    for i in range(3):
        headers = os.environ.get('REQ_HEADER')
        if add_auth:
            req_result = send_authenticated_request(url, data, headers)
        else:
            req_result = requests.post(url, json=data)
        if req_result.status_code < 300:
            if not req_result.headers.get('content-type') == 'application/json':
                logging.debug(req_result.text)
            return req_result
        elif req_result.status_code in accepted_errors:
            logging.warning(req_result.text)
            if debug_print:
                logging.debug(data)
            return req_result
        elif req_result.status_code in fail_on_errors:
            logging.error(f'Error {req_result.status_code}. {req_result.text}')
            if debug_print:
                logging.debug(data)
            logging.error(f'Cannot continue.')
            sys.exit(1)
        else:
            logging.error(f'Error {req_result.status_code}. {req_result.text}')
            if debug_print:
                logging.debug(data)
    logging.error(f'Cannot continue.')
    sys.exit(1)

# ----------------------------------------
#              auth logic
# ----------------------------------------
def send_authenticated_request(url, data, headers):
    if headers is None:
        headers = dict()
    if os.environ.get('CTL_SECRET') is not None:
        headers['Krampus-Auth'] = os.environ.get('CTL_SECRET')
    if os.environ.get('AUTH_HEADER_KEY') is not None:
        if os.environ.get('AUTH_HEADER_VALUE') is not None:
            headers[os.environ.get('AUTH_HEADER_KEY')] = os.environ.get('AUTH_HEADER_VALUE')
            print(headers)
        else:
            logging.warning(f'Environment variable `AUTH_HEADER_KEY` found but environment variable `AUTH_HEADER_VALUE` is missing. This header was not added to the request.')
    if os.environ.get('JWT_USERNAME') is not None:
        headers['Authorization'] = f'Bearer {jwt_token}'
    if headers:
        return requests.post(url, json=data, headers=headers)
    else:
        return requests.post(url, json=data)

def prep_auth(url):
    if os.environ.get('JWT_USERNAME') is not None:
        if os.environ.get('JWT_PASSWORD') is not None:
            req_result = server_req(f'{url}/register-ctl', {'username': os.environ.get('JWT_USERNAME'), 'password': os.environ.get('JWT_PASSWORD')}, fail_on_errors=[415, 401, 400, 403], debug_print=False, add_auth=False)
            req_result = process_rep_response(req_result)
            if 'access_token' in req_result:
                global jwt_token
                jwt_token = req_result['access_token']
                logging.info('JWT Authenication Successful.')
            else:
                logging.error(f'Register failed to return an access token.')
                sys.exit(1)
        else:
            logging.error(f'Authenticating with JWT but password missing. Please add environment variable `JWT_PASSWORD`.')
            sys.exit(1)

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
            collection_data = process_replicate_chunk(req_result['data'], collection_data, f'{server_url}/db-del/{collection}', f'{server_url}/db-edit-row/{collection}')
            # get new data
            req_result = server_req(url, {'limit': limit, 'cursor': req_result['cursor']})
            req_result = process_rep_response(req_result)
        # process last data chunk
        collection_data = process_replicate_chunk(req_result['data'], collection_data, f'{server_url}/db-del/{collection}', f'{server_url}/db-edit-row/{collection}')
        # for collection add all missing data
        for d in collection_data:
            server_req(f'{server_url}/db-add/{collection}', d, fail_on_errors=[409])

def process_rep_response(req_res):
    # if request contains json
    if req_res.headers.get('content-type') == 'application/json':
        # get json
        req_res = req_res.json()
        return req_res
    logging.error(f'Unexpected response from server: content type is not application/json. Cannot continue.')
    logging.debug(f'{req_res.status_code}: {req_res.text}')
    sys.exit(1)

def process_replicate_chunk(response_data, data, del_url, edit_url):
    # sort data so that we find matches based on row_id first
    id_data = []
    no_id_data = []
    for d in data:
        if 'row_id' in data:
            id_data.append(d)
        else:
            no_id_data.append(d)
    data =  id_data + no_id_data

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
        if (match is not None) and not(key in d2 and d2[key] == d1[key]):
            match = False
    for key in set(d2.keys()).difference(set(d1.keys())):
        if (match is not None) and (key != 'row_id') and (d2[key] is not None):
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
            req_result = server_req(f'{server_url}/db-del/{collection}', row, fail_on_errors=[400], accepted_errors=[404])

def delete_multiple(data, server_url):
    for collection in data:
        for row in data[collection]:
            req_result = server_req(f'{server_url}/db-del-multiple/{collection}', row, accepted_errors=[404])

def check_hostconfigs(l, allow_partial=False):
    for row in l:
        KrampusHostConfig(**row)
        if 'targets' not in row:
            row['targets'] = ['all']
    
def check_rules(l, allow_partial=False):
    for row in l:
        if allow_partial:
            allowed_keys = {'identifier', 'policy', 'rule_type', 'custom_msg', 'custom_url', 'notification_app_name', 'cel_expr', 'row_id', 'targets', 'exemptions'}
            rule_keys = set(row.keys())
            if not rule_keys.issubset(allowed_keys):
                logging.error(f'Rule has unknown key(s) {rule_keys.difference(allowed_keys)}.')
                logging.error(f'Possible keys: {allowed_keys}')
                logging.error(f'Rule: {row}')
                sys.exit(1)
        else:
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
def read_input_file(path, allow_partial):
    check_path_exists(path)
    if path.endswith('.yaml') or path.endswith('.yml'):
        return process_yaml(path, allow_partial)
    else:
        logging.error(f'File {path} is not a type of file this script is able to process. Please provide a yaml file.')
        sys.exit(1)

def check_path_exists(path, should_exit=True):
    if os.path.exists(path):
        return True
    elif should_exit:
        logging.error(f'Path {path} does not exist.')
        sys.exit(1)
    else:
        logging.warning(f'Path {path} does not exist. Continuing without access')
        return False

# ----------------------------------------
#                 yaml
# ----------------------------------------
def process_yaml(file_path, allow_partial) -> dict:
    result = read_yaml(file_path)
    check_valid_yaml_dict(result, allow_partial)
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

def check_valid_yaml_dict(data, allow_partial):
    if type(data) != dict:
        logging.error(f'yaml data must be in the form of a dictionary with the top level key being the collection name. This data is of type {type(data)}.')
        sys.exit(1)
    for collection in data:
        collection_data = data[collection]
        if collection == 'rules': 
            check_rules(collection_data, allow_partial)
        elif collection == 'hostconfigs':
            check_hostconfigs(collection_data, )
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
                        help='for each collection, copy this data to the database')
    parser.add_argument('--add', dest='add_path',
                        help='add this data to the database, without creating duplicates')
    parser.add_argument('--edit_fields', dest='edit_fields_path',
                        help='edits specific fields in the data in the database at a specific row id, with the assumption that it exists')
    parser.add_argument('--edit_rows', dest='edit_row_path',
                        help='fully replace the data in the database at a specific id, with the assumption that it exists')
    parser.add_argument('--delete', '-d', dest='del_path',
                        help='removes matches for the given data from the database, with the assumption that exactly one match will be found.')
    parser.add_argument('--delete_multiple', dest='del_path_m',
                           help='removes all matches for the given data from the database, with the assumption that at least one match will be found.')
    parser.add_argument('--limit', '-l', dest='limit', default=50,
                        help='limit for reading from database', type=int)
    parser.add_argument('--output_yaml', '-o', dest='out_path',
                        help='path where a yaml file will be written to reflect the current rules and hostconfigs in krampus.')
    parser.add_argument('--server', '-s', dest='server_url', default="http://0.0.0.0:8000",
                        help='krampus url')
    args = parser.parse_args()
    return args.rep_path, args.add_path, args.edit_row_path, args.edit_fields_path, args.del_path, args.del_path_m, args.limit, args.server_url, args.out_path

# ----------------------------------------
#                 Main
# ----------------------------------------
def main():
    setup_logging()
    rep_path, add_path, edit_row_path, edit_fields_path, del_path, del_path_m, limit, server_url, out_path = process_args()

    if [rep_path, add_path, edit_row_path, edit_fields_path, del_path, del_path_m].count(None) < 4:
        logging.error(f'Please only use one argument that edits the krampus database.')
        sys.exit(1)

    if [rep_path, add_path, edit_row_path, edit_fields_path, del_path, del_path_m, out_path].count(None) > 1:
        prep_auth(server_url)

    if rep_path is not None:
        data = read_input_file(rep_path, False)
        replicate(data, server_url, limit)
    if add_path is not None:
        data = read_input_file(add_path, False)
        add(data, server_url)
    if edit_row_path is not None:
        data = read_input_file(edit_row_path, False)
        edit_row(data, server_url)
    if edit_fields_path is not None:
        data = read_input_file(edit_fields_path, True)
        edit_fields(data, server_url)
    if del_path is not None:
        data = read_input_file(del_path, True)
        delete(data, server_url)
    if del_path_m is not None:
        data = read_input_file(del_path_m, True)
        delete_multiple(data, server_url)
    if out_path is not None:
        write_yaml(out_path, server_url, limit)

if __name__ == '__main__':
    main()