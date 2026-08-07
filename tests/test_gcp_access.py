import sys
import uuid
import logging
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import firestore
from google.cloud import pubsub_v1
from google.cloud import run_v2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def test_firestore_access(project: str):
    logger.info("Running Firestore access tests...")
    db = firestore.Client(project=project)
    doc_ref = db.collection("changemesh_p02").document("feasibility_spike")
    
    test_val = str(uuid.uuid4())
    logger.info("Writing to Firestore...")
    doc_ref.set({"test_id": test_val})
    
    logger.info("Reading from Firestore...")
    doc = doc_ref.get()
    if not doc.exists:
        logger.error("Assertion Failed: Document not found after write.")
        sys.exit(1)
        
    data = doc.to_dict()
    if data.get("test_id") != test_val:
        logger.error("Assertion Failed: Read-back values do not match.")
        sys.exit(1)
        
    logger.info("Firestore assertions passed. Cleaning up...")
    doc_ref.delete()

def test_pubsub_access(project: str):
    logger.info("Running Pub/Sub access tests...")
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    
    topic_id = f"changemesh-p02-topic-{uuid.uuid4().hex[:8]}"
    sub_id = f"changemesh-p02-sub-{uuid.uuid4().hex[:8]}"
    
    topic_path = publisher.topic_path(project, topic_id)
    sub_path = subscriber.subscription_path(project, sub_id)
    
    logger.info(f"Creating topic {topic_path}...")
    publisher.create_topic(request={"name": topic_path})
    
    try:
        logger.info(f"Creating subscription {sub_path}...")
        subscriber.create_subscription(request={"name": sub_path, "topic": topic_path})
        
        test_message = b"changemesh-spike-payload"
        logger.info("Publishing message...")
        future = publisher.publish(topic_path, test_message)
        future.result(timeout=10)
        
        logger.info("Pulling message...")
        response = subscriber.pull(
            request={"subscription": sub_path, "max_messages": 1},
            timeout=10
        )
        
        if not response.received_messages:
            logger.error("Assertion Failed: Zero received messages.")
            sys.exit(1)
            
        received_msg = response.received_messages[0].message.data
        if received_msg != test_message:
            logger.error("Assertion Failed: Payload does not equal published.")
            sys.exit(1)
            
        subscriber.acknowledge(
            request={
                "subscription": sub_path,
                "ack_ids": [response.received_messages[0].ack_id],
            }
        )
        logger.info("Pub/Sub assertions passed.")
    finally:
        logger.info("Cleaning up Pub/Sub resources...")
        try:
            subscriber.delete_subscription(request={"name": sub_path})
        except Exception as e:
            logger.warning(f"Cleanup error (subscription): {e}")
        try:
            publisher.delete_topic(request={"name": topic_path})
        except Exception as e:
            logger.warning(f"Cleanup error (topic): {e}")

def test_cloud_run_access(project: str):
    logger.info("Running Cloud Run Admin access tests...")
    client = run_v2.ServicesClient()
    parent = f"projects/{project}/locations/us-central1"
    
    logger.info("Listing Cloud Run services to verify admin access...")
    request = run_v2.ListServicesRequest(parent=parent)
    try:
        page_result = client.list_services(request=request)
        # Just enumerating the first page confirms admin viewer access
        for service in page_result:
            break
        logger.info("Cloud Run Admin access verified.")
    except Exception as e:
        logger.error(f"Assertion Failed: Could not list Cloud Run services. {e}")
        sys.exit(1)

def run_tests():
    logger.info("Starting P-02.04 GCP Access Tests...")
    try:
        creds, project = default()
        logger.info(f"GCP Authentication successful. Project: {project}")
        
        if not project:
            logger.error("FATAL: Project is None. Cannot run tests.")
            sys.exit(1)
            
        test_firestore_access(project)
        test_pubsub_access(project)
        test_cloud_run_access(project)
        
        logger.info("All GCP access tests passed successfully.")
        sys.exit(0)
    except DefaultCredentialsError as e:
        logger.error(f"FATAL: Application Default Credentials not found.")
        logger.error(f"Cannot run real GCP access tests without authentication. Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"FATAL: Test execution failed. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
