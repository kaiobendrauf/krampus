import logging
import os

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def auth_ctl(request):
    # Given a request, returns True if the ctl request can be authenticated
    return auth_check(os.environ.get('CTL_SECRET'), request)

def auth_sync(request, machine_id: str=None):
    # Given a request and optionally a machine_id, returns True if the sync request can be authenticated
    return auth_check(os.environ.get('SYNC_SECRET'), request)

def register(request):
    '''
    If applicable and the request is able to authenticate returns information needed for further authentication (eg a token)

    Parameters:
        request: flask request object

    Returns:
        dict: dict containing the needed information or description of action taken under 'msg' key
        int: http status code reflecting the success of the attempted action
    '''
    return {'msg':'No registration required'}, 200

def setup(is_ctl: bool, data=None):
    # Sets up authentication for either krampusctl or the syncs, based on the is_ctl variable
    if is_ctl:
        if os.environ.get('CTL_SECRET') is None:
            logging.error(f'Trying to set up header as authentication but missing environ variable "CTL_SECRET"'.)
            sys.exit(1)
    else:
        if os.environ.get('SYNC_SECRET') is None:
            logging.error(f'Trying to set up header as authentication but missing environ variable "SYNC_SECRET"'.)
            sys.exit(1)


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------

def auth_check(secret: str, request):
    return request.headers.get('Krampus-Auth') and (request.headers.get('Krampus-Auth') == secret)