# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
import logging
import sys


def send_events(data: list):
    for event in data:
        if 'file_name' not in event:
            logging.error('Event without file_name cannot be stored.')
            logging.debug(event)
        else:
            name = event['file_name']
            decision = event['decision']
            rows = db.lookup('eventssummary', {'file_name': name})
            if len(rows) == 0:
                # add row
                db.add('eventssummary', {'file_name': name, decision: 1})
            elif len(rows) == 1:
                row = rows[0]
                # edit row
                if decision in row and (not (row[decision] is None)):
                    n = int(row[decision])
                    db.edit_fields('eventssummary', {'row_id': row['row_id'], decision: n + 1})
                else:
                    db.edit_fields('eventssummary', {'row_id': row['row_id'], decision: 1})
            else:
                # error
                logging.error('More than one eventssummary for {name}.')

                row = rows[0]
                logging.warning('Will update eventssummary for {name} at row_id {row["row_id"]}.')
                if decision in row and (not (row[decision] is None)):
                    n = int(row[decision])
                    db.edit_fields('eventssummary', {'row_id': row['row_id'], decision: n + 1})
                else:
                    db.edit_fields('eventssummary', {'row_id': row['row_id'], decision: 1})
    
def setup(data):
    # Sets up the database object
    global db
    db = data

    if not db.is_summary_event_handler:
        logging.error('Krampus (summary) is chosen as the event handler but the chosen database is not set up for event handling.')
        sys.exit(1)
    
# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------