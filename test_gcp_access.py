import os
import sys
from google.cloud import firestore
from google.cloud import pubsub_v1
from google.cloud import run_v2

PROJECT_ID = "project-af5e1c99-3bc4-424f-b53"
REGION = "europe-west3"

def test_firestore():
    print(f"Testing Firestore in project {PROJECT_ID}...")
    try:
        db = firestore.Client(project=PROJECT_ID)
        doc_ref = db.collection(u'changemesh_spike').document(u'test_doc')
        doc_ref.set({u'status': u'active', u'type': u'spike'})
        print("  - Document written successfully.")
        
        doc = doc_ref.get()
        if doc.exists:
            print(f"  - Document read successfully: {doc.to_dict()}")
        else:
            print("  - Document NOT found!")
            
        doc_ref.delete()
        print("  - Document deleted successfully.")
        return True
    except Exception as e:
        print(f"  - Firestore error: {e}")
        return False

def test_pubsub():
    print(f"Testing Pub/Sub in project {PROJECT_ID}...")
    try:
        publisher = pubsub_v1.PublisherClient()
        subscriber = pubsub_v1.SubscriberClient()
        topic_path = publisher.topic_path(PROJECT_ID, "changemesh_spike_topic")
        subscription_path = subscriber.subscription_path(PROJECT_ID, "changemesh_spike_sub")
        
        # Try to create topic
        try:
            topic = publisher.create_topic(request={"name": topic_path})
            print(f"  - Topic created: {topic.name}")
        except Exception as create_e:
            if "AlreadyExists" in str(create_e):
                print("  - Topic already exists.")
            else:
                raise create_e
                
        # Try to create subscription
        try:
            subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
            print(f"  - Subscription created: {subscription_path}")
        except Exception as create_e:
            if "AlreadyExists" in str(create_e):
                print("  - Subscription already exists.")
            else:
                raise create_e
        
        # Try to publish
        data = b"Hello from ChangeMesh Spike"
        future = publisher.publish(topic_path, data)
        message_id = future.result()
        print(f"  - Message published. ID: {message_id}")
        
        # Try to consume
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 1},
            timeout=10.0,
        )
        for msg in response.received_messages:
            print(f"  - Message consumed: {msg.message.data}")
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": [msg.ack_id]}
            )
            print("  - Message acknowledged.")
        
        # Cleanup
        subscriber.delete_subscription(request={"subscription": subscription_path})
        print("  - Subscription deleted successfully.")
        publisher.delete_topic(request={"topic": topic_path})
        print("  - Topic deleted successfully.")
        return True
    except Exception as e:
        print(f"  - Pub/Sub error: {e}")
        return False

def test_cloud_run():
    print(f"Testing Cloud Run in project {PROJECT_ID} region {REGION}...")
    try:
        client = run_v2.ServicesClient()
        parent = f"projects/{PROJECT_ID}/locations/{REGION}"
        service_id = "changemesh-spike-svc"
        service_name = f"{parent}/services/{service_id}"
        
        print(f"  - Attempting to create Cloud Run service '{service_id}'...")
        service = run_v2.Service(
            template=run_v2.RevisionTemplate(
                containers=[run_v2.Container(image="us-docker.pkg.dev/cloudrun/container/hello")]
            )
        )
        request = run_v2.CreateServiceRequest(
            parent=parent,
            service_id=service_id,
            service=service
        )
        
        # Deploy service
        operation = client.create_service(request=request)
        print("  - Deployment operation started, waiting for completion...")
        response = operation.result()
        print(f"  - Success! Service deployed at: {response.uri}")
        
        # Cleanup
        print("  - Deleting disposable service...")
        del_request = run_v2.DeleteServiceRequest(name=service_name)
        del_operation = client.delete_service(request=del_request)
        del_operation.result()
        print("  - Disposable service deleted successfully.")
        return True
    except Exception as e:
        print(f"  - Cloud Run error: {e}")
        return False

if __name__ == "__main__":
    fs_ok = test_firestore()
    ps_ok = test_pubsub()
    cr_ok = test_cloud_run()
    
    if fs_ok and ps_ok and cr_ok:
        print("\nAll required Google Cloud services are accessible!")
        sys.exit(0)
    else:
        print("\nSome services failed. Check logs above.")
        sys.exit(1)
