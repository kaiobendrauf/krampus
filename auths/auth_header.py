# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def auth_ctl(request):
    # Given a request, returns True if the ctl request can be authenticated
    return auth_check(ctl_secret, request)

def auth_sync(request, machine_id: str=None):
    # Given a request and optionally a machine_id, returns True if the sync request can be authenticated
    return auth_check(sync_secret, request)

def setup(is_ctl: bool, data=None):
    if is_ctl:
        global ctl_secret 
        ctl_secret = data
    else:
        global sync_secret 
        sync_secret = data


# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------

def auth_check(secret: str, request):
    return request.headers.get('Krampus-Auth') and (request.headers.get('Krampus-Auth') == secret)