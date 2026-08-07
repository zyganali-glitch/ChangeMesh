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

    # Call Gemini API to list models
    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(models_url)
    model_name = "models/gemini-1.5-pro" # fallback
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            models = [m['name'] for m in data.get('models', [])]
            for m in models:
                if 'gemini-3.5' in m:
                    model_name = m
                    break
    except Exception as e:
        print("Error fetching models:", e)

    print("Using model:", model_name)

    # Structured output call
    generate_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": "Return a JSON object with two fields: 'status' (string, value 'OK') and 'project' (string, value 'ChangeMesh')."}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(generate_url, data=data, headers={"Content-Type": "application/json"})
    
    start_time = time.time()
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode()
            latency = int((time.time() - start_time) * 1000)
            print("Response received successfully!")
            print("Latency:", latency, "ms")
            
            # Save artifact
            os.makedirs("docs", exist_ok=True)
            with open("docs/P-02.02_evidence.json", "w") as f:
                json.dump({
                    "model_id": model_name,
                    "latency_ms": latency,
                    "region": "europe-west3 (API Key global endpoint)",
                    "sdk_version": "urllib (REST API)",
                    "response": json.loads(resp_body)
                }, f, indent=2)
            print("Evidence saved to docs/P-02.02_evidence.json")
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code, e.read().decode())
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
