# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def auth_ctl(request):
    # Given a request, returns True if the ctl request can be authenticated
    return True

def auth_sync(request, machine_id: str=None):
    # Given a request and optionally a machine_id, returns True if the sync request can be authenticated
    return True

def setup(is_ctl: bool, data=None):
    return

# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------