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
        topic_path = publisher.topic_path(PROJECT_ID, "changemesh_spike_topic")
        
        # Try to create topic
        try:
            topic = publisher.create_topic(request={"name": topic_path})
            print(f"  - Topic created: {topic.name}")
        except Exception as create_e:
            if "AlreadyExists" in str(create_e):
                print("  - Topic already exists.")
            else:
                raise create_e
        
        # Try to publish
        data = b"Hello from ChangeMesh Spike"
        future = publisher.publish(topic_path, data)
        message_id = future.result()
        print(f"  - Message published. ID: {message_id}")
        
        # Try to delete topic
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
        
        # Just listing services to verify API access is enabled. 
        # Creating a service requires detailed config, listing is a good enough proxy for API access.
        print(f"  - Listing Cloud Run services in {parent}...")
        request = run_v2.ListServicesRequest(parent=parent)
        page_result = client.list_services(request=request)
        
        count = 0
        for response in page_result:
            count += 1
            
        print(f"  - Success! Found {count} services (API is accessible).")
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
