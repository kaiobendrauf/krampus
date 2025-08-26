from concurrent import futures
from google.cloud import pubsub_v1
import logging
from typing import Callable

publisher = pubsub_v1.PublisherClient()

# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def send_events(data: list):
	publish_futures = []
	for event in data:
	    event = str(event)
	    # When you publish a message, the client returns a future.
	    publish_future = publisher.publish(topic_path, event.encode('utf-8'))
	    # Non-blocking. Publish failures are handled in the callback function.
	    publish_future.add_done_callback(get_callback(publish_future, event))
	    publish_futures.append(publish_future)

	# Wait for all the publish futures to resolve before exiting.
	futures.wait(publish_futures, return_when=futures.ALL_COMPLETED)

	print(f'Published messages with error handler to {topic_path}.')


def setup():
	# Sets up the Pub/Sub connection, checking that environmental variables 'PUB_SUB_PROJ_ID' 'PUB_SUB_TOPIC_ID' and are found
    project_id = os.environ.get('PUB_SUB_PROJ_ID')
    topic_id = os.environ.get('PUB_SUB_TOPIC_ID')
    if not project_id:
        logging.error('A Pub/Sub project id is required to connect to publish events to a Pub/Sub topic, please add this as the environmental variable "PUB_SUB_PROJ_ID".')
        sys.exit(1)
    if not topic_id:
        logging.error('A Pub/Sub topic id is required to connect to publish events to a Pub/Sub topic, please add this as the environmental variable "PUB_SUB_TOPIC_ID".')
        sys.exit(1)

    global topic_path
    topic_path = publisher.topic_path(project_id, topic_id)

# --------------------------------------------------------------------------------
#                                Helper Functions
# --------------------------------------------------------------------------------
def get_callback(
    publish_future: pubsub_v1.publisher.futures.Future, data: str
) -> Callable[[pubsub_v1.publisher.futures.Future], None]:
    def callback(publish_future: pubsub_v1.publisher.futures.Future) -> None:
        try:
            # Wait 60 seconds for the publish call to succeed.
            logging.debug(publish_future.result(timeout=60))
        except futures.TimeoutError:
            logging.error(f'Publishing {data} timed out.')
    return callback