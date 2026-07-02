# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def send_events(data: list):
    for event in data:
        decision = event['decision']
        summary = db.lookup_by_id('events_summary', event['file_name'])
        if summary:
            if decision in summary:
                summary[decision] += 1
            else:
                summary[decision] = 1
            db.edit('events_summary', summary, summary['file_name'])
        else:
            summary = dict()
            summary['file_name'] = event['file_name']
            summary[decision] = 1
            db.add('events_summary', summary, summary['file_name'])
    return None
    
def setup(data):
    # Sets up the database object
    global db
    db = data

    if not db.is_event_handler:
        logging.error('Krampus (summary) is chosen as the event handler but the chosen database is not set up for event handling.')
        sys.exit(1)
    
# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------