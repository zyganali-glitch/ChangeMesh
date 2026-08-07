import sys
from google.cloud import service_usage_v1

PROJECT_ID = "project-af5e1c99-3bc4-424f-b53"

def check_service(client: service_usage_v1.ServiceUsageClient, service_name: str, display_name: str):
    print(f"\nChecking {display_name} ({service_name})...")
    request = service_usage_v1.GetServiceRequest(
        name=f"projects/{PROJECT_ID}/services/{service_name}"
    )
    try:
        response = client.get_service(request=request)
        if response.state == service_usage_v1.State.ENABLED:
            print(f"  - Status: AVAILABLE (Enabled)")
            return "AVAILABLE"
        else:
            print(f"  - Status: DISABLED (Found but not enabled)")
            return "DISABLED"
    except Exception as e:
        err_msg = str(e)
        if "PermissionDenied" in err_msg or "403" in err_msg:
            print(f"  - Status: PERMISSION_BLOCKED (No access to enable/view)")
            return "PERMISSION_BLOCKED"
        elif "Not found" in err_msg or "404" in err_msg:
            print(f"  - Status: PREVIEW_BLOCKED (Service does not exist publicly or in this region)")
            return "PREVIEW_BLOCKED"
        else:
            print(f"  - Status: ERROR ({err_msg})")
            return "ERROR"

def main():
    client = service_usage_v1.ServiceUsageClient()
    
    # 1. Agent Runtime (Vertex AI)
    check_service(client, "aiplatform.googleapis.com", "Agent Runtime (Vertex AI Reasoning Engine)")
    
    # 2. Agent Registry
    registry_status = check_service(client, "agentregistry.googleapis.com", "Agent Registry")
    
    # 3. Agent Gateway (Network Services)
    gw_status = check_service(client, "networkservices.googleapis.com", "Agent Gateway (Network Services)")
    
    # 4. Model Armor
    armor_status = check_service(client, "modelarmor.googleapis.com", "Model Armor")
    
    print("\n--- Final Assessment ---")
    if registry_status == "PREVIEW_BLOCKED" or gw_status == "PREVIEW_BLOCKED":
        print("CRITICAL: Some core ADK Agent Platform APIs are not publicly available yet.")
        print("We must mark these as DEFERRED/PREVIEW_BLOCKED and use local adapters for the MVP.")
        sys.exit(1)
    else:
        print("All APIs verified.")
        sys.exit(0)

if __name__ == "__main__":
    main()
