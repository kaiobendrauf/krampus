#!/usr/bin/env python3

import json
import logging
import optparse
import os
import requests
import sys
import yaml

# ----------------------------------------
#          server requests
# ----------------------------------------
def server_req(url, data, accept_any_response=False):
    req_result = requests.post(url, json = data)
    result = req_result
    if accept_any_response or req_result.status_code < 300:
        if not req_result.headers.get('content-type') == 'application/json':
            logging.debug(req_result.text)
        return req_result
    else:
        logging.error(f'Error {req_result.status_code}. {req_result.text}')
        logging.error(f'Cannot continue.')
        sys.exit(1)

# ----------------------------------------
#               DB logic
# ----------------------------------------
def replicate(data, server_url, limit):
    for collection in data:
        collection_data = data[collection]
        check_hostconfigs(collection_data)
        url = server_url + f'/db-read/{collection}'
        req_result = server_req(url, {'limit': limit})
        req_result = process_rep_response(req_result)
        while 'cursor' in req_result:
            # still reading
            # process data (note data that does not need to be added, delete what needs to be deleted)
            collection_data = process_replicate_chunk(req_result['data'], collection_data, f'{server_url}/db-del/{collection}')
            # get new data
            req_result = server_req(url, {'limit': limit, 'cursor':req_result['cursor']})
            req_result = process_rep_response(req_result)
        # process last data chunk
        collection_data = process_replicate_chunk(req_result['data'], collection_data, f'{server_url}/db-del/{collection}')
        # for collection add all missing data
        for row in collection_data:
            server_req(f'{server_url}/db-add/{collection}', row)

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

def process_replicate_chunk(response_data, collection_data, del_url): 
    for row in response_data:
        if row not in collection_data:
            server_req(del_url, row)
        else:
            collection_data.remove(row)
    return collection_data


def add(data, server_url):
    for collection in data:
        logging.debug(f'Adding to {collection}')
        check_hostconfigs(data[collection])
        for row in data[collection]:
            req_result = server_req(f'{server_url}/db-add/{collection}', row)
            if 'already' in req_result.text:
                logging.warning(req_result.text)
                logging.debug(row)

def delete(data, server_url):
    for collection in data:
        for row in data[collection]:
            req_result = server_req(f'{server_url}/db-del/{collection}', row, True)
            if req_result.status_code == 404:
                logging.warning(req_result.text)
                logging.debug(row)
            elif req_result.status_code == 400:
                logging.warning(req_result.text)
                logging.debug(row)
            elif req_result.status_code >= 300:
                logging.error(f'Error {req_result.status_code}. {req_result.text}')
                logging.error(f'Cannot continue.')
                sys.exit(1)

def delete_multiple(data, server_url):
    for collection in data:
        for row in data[collection]:
            req_result = server_req(f'{server_url}/db-del-multiple/{collection}', row, True)
            if req_result.status_code == 404:
                logging.warning(req_result.text)
                logging.debug(row)
            elif req_result.status_code >= 300:
                logging.error(f'Error {req_result.status_code}. {req_result.text}')
                logging.error(f'Cannot continue.')
                sys.exit(1)

def check_hostconfigs(l):
    targets = []
    for row in l:
        if 'target' in row:
            if row['target'] in targets:
                # conflict
                logging.error('Two hostconfigs have the same target. Please ensure there is only one hotconfig per target.')
                sys.etit(1)
            else:
                targets += [row['target']]


# ----------------------------------------
#                 File reader
# ----------------------------------------
def read_input_file(path):
    check_path_exists(path)
    if path.endswith('.yaml') or path.endswith('.yml'):
        return process_yaml(path)
    else:
        logging.error(f'File {path} is not a type of file this script is able to process. Please provide a yaml file.')

def check_path_exists(path, exit=True):
    if os.path.exists(path):
        return True
    elif exit:
        logging.error(f'Path {path} dpes not exist.')
        sys.exit(1)
    else:
        logging.warning(f'Path {path} dpes not exist. Continueing without access')
        return False

# ----------------------------------------
#                 yaml
# ----------------------------------------
def process_yaml(file_path) -> dict:
    result = read_yaml(file_path)
    check_valid_yaml_dict(result)
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

def check_valid_yaml_dict(data):
    if type(data) != dict:
        logging.error(f'yaml data must be in the form of a dictionary with the top level key being the collection name. This data is of type {type(data)}.')
        sys.exit(1)
    for collection in data:
        collection_data = data[collection]
        if type(collection_data) != list:
            logging.error(f'In the yaml for each collection, the value must be a list of rules or configurations. Instead the value has type {type(collection_data)}.')
            sys.exit(1)
        for el in collection_data:
            if type(el) != dict:
                logging.error(f'In the yaml for each collection, the value must be a list of rules or configurations, which must have type dict. Instead the elements of {key}s have type {type(el)}.')
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
def process_options():
    parser = optparse.OptionParser()
    parser.set_usage('Usage: %prog [options]')
    parser.add_option('--replicate', '-r', dest='rep_path',
                        help='copy this data to the database')
    parser.add_option('--add', '-a', dest='add_path',
                        help='add this data to the database, without creating duplicates')
    parser.add_option('--delete', '-d', dest='del_path',
                        help='remove this data from the database')
    parser.add_option('--deletemultiple', dest='del_path_m',
                           help='remove all matches for this data from the database')
    parser.add_option('--limit', '-l', dest='limit', default=50,
                        help='limit for reading from database')
    parser.add_option('--server', '-s', dest='server_url', default="http://0.0.0.0:3000",
                        help='limit for reading from database')
    options, _ = parser.parse_args()
    return options.rep_path, options.add_path, options.del_path, options.del_path_m, int(options.limit), options.server_url

# ----------------------------------------
#                 Main
# ----------------------------------------
def main():
    setup_logging()
    rep_path, add_path, del_path, del_path_m, limit, server_url = process_options()

    if rep_path:
        data = read_input_file(rep_path)
        replicate(data, server_url, limit)
    if add_path:
        data = read_input_file(add_path)
        add(data, server_url)
    if del_path:
        data = read_input_file(del_path)
        delete(data, server_url)
    if del_path_m:
        data = read_input_file(del_path_m)
        delete_multiple(data, server_url)


if __name__ == '__main__':
    main()