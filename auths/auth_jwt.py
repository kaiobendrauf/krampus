import hmac
import logging
import os
import sys

import flask
import jwt

from datetime import datetime, timedelta, timezone
# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def auth_ctl(request):
    # Given a request, returns True if the ctl request can be authenticated
    minutes = os.environ.get('JWT_EXP_MIN')
    if minutes is None:
        minutes = 5 
    auth = request.headers.get('Authorization')
    if auth is not None:
        if auth.startswith('Bearer '):
            token = auth.removeprefix('Bearer ')
            try:
                decode = jwt.decode(token, os.environ.get('JWT_SECRET'), options={'require': ['user', 'iat', 'exp']}, algorithms=["HS256"])
                if hmac.compare_digest(decode['user'], os.environ.get('JWT_USERNAME')):
                    if datetime.fromtimestamp(decode['iat']) + timedelta(minutes=int(minutes)) == datetime.fromtimestamp(decode['exp']):
                        return True
                    else:
                        logging.warning('JWT authentication failed because unexpected iat or exp.')
                else:
                        logging.warning('JWT authentication failed because unknown username.')
            except Exception as e:
                logging.warning(f'JWT authentication failed with error {e}')
    return False


def auth_sync(request, machine_id: str | None = None):
    # Given a request and optionally a machine_id, returns True if the sync request can be authenticated
    return False

def register(request):
    '''
    If applicable and the request is able to authenticate returns information needed for further authentication (eg a token)

    Parameters:
        request: flask request object

    Returns:
        dict: dict containing the needed information or description of action taken under 'msg' key
        int: http status code reflecting the success of the attempted action
    '''
    minutes = os.environ.get('JWT_EXP_MIN')
    if minutes is None:
        minutes = 5 

    if request.content_type == 'application/json':
        data = flask.request.get_json()
    else:
        return {'msg': 'Expected data as json.'}, 415

    if 'username' in data:
        if 'password' in data:
            if data['username'] != os.environ.get('JWT_USERNAME') or data['password'] != os.environ.get('JWT_PASSWORD'):
                return {'msg': 'Invalid credentials.'}, 401
        else:
            return {'msg': 'Missing password.'}, 400 
    else:
        return {'msg': 'Missing username.'}, 400 

    d = {
        'user': os.environ.get('JWT_USERNAME'), 
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(minutes=int(minutes))}

    access_token = jwt.encode(d, os.environ.get('JWT_SECRET'), algorithm='HS256')
    return {'access_token': access_token}, 200
 

def setup(is_ctl: bool, data=None):
    # Sets up authentication for either krampusctl or the syncs, based on the is_ctl variable
    if is_ctl:
        for s in ['JWT_USERNAME', 'JWT_PASSWORD', 'JWT_SECRET']:
            if os.environ.get(s) is None:
                logging.error(f'Trying to set up header as authentication but missing environmental variable {s}')
                sys.exit(1)
        if os.environ.get('JWT_EXP_MIN') is None:
            logging.warning('No environment variable `JWT_EXP_MIN` given. Using default of 5.')
    else:
        logging.error(f'JWT authentication only supports authenticating krampusctl, you cannot authenticate santa sync requests with this authentication type.')
        sys.exit(1)


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------

def auth_check(secret: str, request):
    return request.headers.get('Krampus-Auth') and (request.headers.get('Krampus-Auth') == secret)