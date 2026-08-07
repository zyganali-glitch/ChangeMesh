import urllib.request
import json
import time
import os

def main():
    try:
        with open("api_key.txt", "r") as f:
            api_key = f.read().strip()
    except Exception as e:
        print("Could not read API key:", e)
        return

    project_id = "project-af5e1c99-3bc4-424f-b53"
    region = "europe-west3"
    model_name = "gemini-1.5-flash"
    
    # Vertex AI Endpoint
    url = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{region}/publishers/google/models/{model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": "Return a JSON object with two fields: 'status' (string, value 'OK') and 'project' (string, value 'ChangeMesh')."}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    start_time = time.time()
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode()
            latency = int((time.time() - start_time) * 1000)
            print("Vertex AI Response received successfully!")
            print("Latency:", latency, "ms")
            
            # Save artifact
            os.makedirs("docs", exist_ok=True)
            with open("docs/P-02.02_evidence.json", "w") as f:
                json.dump({
                    "model_id": model_name,
                    "latency_ms": latency,
                    "region": region,
                    "sdk_version": "urllib (Vertex AI REST API via API Key)",
                    "response": json.loads(resp_body)
                }, f, indent=2)
            print("Evidence saved to docs/P-02.02_evidence.json")
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code, e.read().decode())
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
