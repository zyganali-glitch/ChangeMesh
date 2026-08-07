"""
P-02.03 — Google ADK Spike
Demonstrates a real ADK agent using `google.adk.agents.LlmAgent`.
Fails explicitly if Google Cloud ADC credentials are not configured,
as required by the governance rules (no silent failures or mock workarounds).
"""
import sys
import logging
from google.adk.agents import LlmAgent
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def verify_schema_change(table_name: str, requested_columns: list[str]) -> dict:
    """Tool to verify if a schema change is permitted."""
    logger.info(f"Tool called: verify_schema_change for table '{table_name}'")
    forbidden = ["credit_card", "ssn", "password_hash"]
    violations = [col for col in requested_columns if col in forbidden]
    if violations:
        return {"permitted": False, "reason": f"Forbidden columns requested: {violations}"}
    return {"permitted": True, "reason": "No forbidden columns found."}

def main():
    logger.info("Starting P-02.03 Google ADK Spike...")
    
    try:
        # 1. Enforce GCP authentication (Governance requirement: no mocks)
        logger.info("Checking Application Default Credentials...")
        creds, project = default()
        logger.info(f"GCP Authentication successful. Project: {project}")
    except DefaultCredentialsError as e:
        logger.error(f"FATAL: Application Default Credentials not found.")
        logger.error(f"Cannot run real ADK spike without authentication. Error: {e}")
        # The agent MUST exit non-zero here to block P-04 eligibility until fixed.
        logger.error("Result: FAIL. Please configure GCP ADC via 'gcloud auth application-default login'.")
        sys.exit(1)
        
    try:
        # 2. Initialize the real ADK Agent
        logger.info("Initializing ADK LlmAgent...")
        agent = LlmAgent(
            model="gemini-3.5-flash",
            instructions="You are a schema verification agent. Use the verify_schema_change tool to check database change requests.",
            tools=[verify_schema_change]
        )
        
        # 3. Execute a tool-calling scenario
        prompt = "Please add a 'credit_card' column to the 'users' table."
        logger.info(f"Sending prompt to ADK Agent: '{prompt}'")
        
        response = agent.run(prompt)
        
        logger.info(f"Agent Response: {response.text}")
        logger.info("Result: PASS.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"FATAL: ADK execution failed. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
