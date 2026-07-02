# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def send_events(data: list):
    for event in data:
        db.add('events_full', event)
    return None
    
def setup(data):
    # Sets up the database object
    global db
    db = data

    if not db.is_event_handler:
        logging.error('Krampus (full) is chosen as the event handler but the chosen database is not set up for event handling.')
        sys.exit(1)
# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------