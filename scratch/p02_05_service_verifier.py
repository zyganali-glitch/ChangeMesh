import sys
import logging
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import AuthorizedSession
from google.cloud import logging as cloud_logging
from google.cloud import trace_v2
from google.api_core.exceptions import GoogleAPICallError

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def make_request(url, method="GET"):
    try:
        creds, project = default()
        authed_session = AuthorizedSession(creds)
        if method == "GET":
            resp = authed_session.get(url)
        else:
            resp = authed_session.post(url)
        return resp.status_code, resp.text
    except Exception as e:
        if "getaddrinfo failed" in str(e) or "Max retries exceeded" in str(e):
            return 0, "PREVIEW_BLOCKED_DNS"
        return 0, str(e)

def classify(status, text):
    if text == "PREVIEW_BLOCKED_DNS":
        return "PREVIEW_BLOCKED"
    if status == 200:
        return "AVAILABLE"
    elif status in [401, 403]:
        return "PERMISSION_BLOCKED"
    else:
        return "UNCLASSIFIABLE"

def probe_agent_runtime(project):
    doc_url = "https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview"
    api_resource = "aiplatform.googleapis.com / reasoningEngines"
    probe_used = "GET https://aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/reasoningEngines"
    url = f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/reasoningEngines"
    status, text = make_request(url)
    avail = classify(status, text)
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", f"HTTP {status}"

def probe_memory_bank(project):
    doc_url = "https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank"
    api_resource = "aiplatform.googleapis.com / reasoningEngines/{id}/memories"
    probe_used = "POST https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/us-central1/reasoningEngines/{id}/memories:retrieve"
    avail = "DEFERRED"
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", "Requires ReasoningEngine instance, none deployed yet"

def probe_agent_registry(project):
    doc_url = "https://cloud.google.com/agent-registry/docs"
    api_resource = "agentregistry.googleapis.com / mcpServers"
    probe_used = "GET https://agentregistry.googleapis.com/v1/projects/{project}/locations/global/mcpServers"
    url = f"https://agentregistry.googleapis.com/v1/projects/{project}/locations/global/mcpServers"
    status, text = make_request(url)
    avail = classify(status, text)
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", f"HTTP {status}"

def probe_agent_identity(project):
    doc_url = "https://cloud.google.com/iam/docs/agent-identity"
    api_resource = "agentidentity.googleapis.com / authProviders"
    probe_used = "GET https://agentidentity.googleapis.com/v1/projects/{project}/locations/global/authProviders"
    url = f"https://agentidentity.googleapis.com/v1/projects/{project}/locations/global/authProviders"
    status, text = make_request(url)
    avail = classify(status, text)
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", f"HTTP {status}"

def probe_agent_gateway(project):
    doc_url = "https://cloud.google.com/network-services/docs/agent-gateway"
    api_resource = "networkservices.googleapis.com / agentGateways"
    probe_used = "GET https://networkservices.googleapis.com/v1/projects/{project}/locations/global/agentGateways"
    url = f"https://networkservices.googleapis.com/v1/projects/{project}/locations/global/agentGateways"
    status, text = make_request(url)
    avail = classify(status, text)
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", f"HTTP {status}"

def probe_model_armor(project):
    doc_url = "https://cloud.google.com/model-armor/docs"
    api_resource = "modelarmor.googleapis.com / templates"
    probe_used = "GET https://modelarmor.googleapis.com/v1/projects/{project}/locations/us-central1/templates"
    url = f"https://modelarmor.googleapis.com/v1/projects/{project}/locations/us-central1/templates"
    status, text = make_request(url)
    avail = classify(status, text)
    return doc_url, api_resource, probe_used, avail, "NOT_RUN", f"HTTP {status}"

def probe_observability(project):
    doc_url = "https://cloud.google.com/vertex-ai/generative-ai/docs/agent-builder/observability"
    api_resource = "logging.googleapis.com + cloudtrace.googleapis.com"
    probe_used = "Cloud Logging SDK list_entries + Cloud Trace SDK batch_write_spans"
    try:
        creds, _ = default()
        log_client = cloud_logging.Client(credentials=creds, project=project)
        entries = list(log_client.list_entries(max_results=1))
        
        trace_client = trace_v2.TraceServiceClient(credentials=creds)
        trace_client.batch_write_spans(name=f"projects/{project}", spans=[])
        return doc_url, api_resource, probe_used, "AVAILABLE", "NOT_RUN", "Logging & Trace SDK calls succeeded"
    except GoogleAPICallError as e:
        if e.code in [401, 403]:
            return doc_url, api_resource, probe_used, "PERMISSION_BLOCKED", "NOT_RUN", f"API Error: {e.code}"
        return doc_url, api_resource, probe_used, "UNCLASSIFIABLE", "NOT_RUN", f"API Error: {e.code} - {e.message}"
    except Exception as e:
        if "getaddrinfo" in str(e) or "WSA Error" in str(e):
            return doc_url, api_resource, probe_used, "PREVIEW_BLOCKED", "NOT_RUN", f"SDK Error: DNS blocked - {e}"
        return doc_url, api_resource, probe_used, "UNCLASSIFIABLE", "NOT_RUN", f"SDK Error: {e}"

def main():
    logger.info("Starting P-02.05 Seven-Component Service Verifier...")
    
    try:
        creds, project = default()
    except DefaultCredentialsError:
        logger.error("FATAL: Application Default Credentials not found.")
        sys.exit(1)
        
    COMPONENTS = [
        {"name": "Agent Runtime", "probe": probe_agent_runtime},
        {"name": "Memory Bank", "probe": probe_memory_bank},
        {"name": "Agent Registry", "probe": probe_agent_registry},
        {"name": "Agent Identity", "probe": probe_agent_identity},
        {"name": "Agent Gateway", "probe": probe_agent_gateway},
        {"name": "Model Armor", "probe": probe_model_armor},
        {"name": "Observability", "probe": probe_observability},
    ]

    print("| Component | Doc URL | Exact API / Resource | Probe Used | Availability | Integration State | Response / Error |")
    print("|---|---|---|---|---|---|---|")
    
    has_unclassifiable = False
    
    for comp in COMPONENTS:
        doc_url, api_resource, probe_used, avail, state, response = comp['probe'](project)
        print(f"| {comp['name']} | {doc_url} | {api_resource} | {probe_used} | {avail} | {state} | {response} |")
        if avail == "UNCLASSIFIABLE":
            has_unclassifiable = True
            
    if has_unclassifiable:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
