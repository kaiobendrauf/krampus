# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def auth_ctl(request):
    # Given a request, returns True if the ctl request can be authenticated
    return True

def auth_sync(request, machine_id: str=None):
    # Given a request and optionally a machine_id, returns True if the sync request can be authenticated
    return True

def register(request) -> tuple[dict, int]:
    '''
    If applicable and the request is able to authenticate returns information needed for further authentication (eg a token)

    Parameters:
        request: flask request object

    Returns:
        dict: dict containing the needed information or description of action taken under 'msg' key
        int: http status code reflecting the success of the attempted action
    '''
    return {'msg':'No registration required'}, 200

def setup(is_ctl: bool):
    # Sets up authentication for either krampusctl or the syncs, based on the is_ctl variable
    return

# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------