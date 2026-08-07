import sys
import logging
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.models.google_llm import Gemini
from google.genai.types import Content, Part
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class SchemaVerificationResult(BaseModel):
    permitted: bool
    reason: str

def verify_schema_change(table_name: str, requested_columns: list[str]) -> SchemaVerificationResult:
    """Tool to verify if a schema change is permitted."""
    logger.info(f"Tool called: verify_schema_change for table '{table_name}'")
    forbidden = ["credit_card", "ssn", "password_hash"]
    violations = [col for col in requested_columns if col in forbidden]
    if violations:
        return SchemaVerificationResult(permitted=False, reason=f"Forbidden columns requested: {violations}")
    return SchemaVerificationResult(permitted=True, reason="No forbidden columns found.")

def main():
    logger.info("Starting P-02.03 Google ADK Spike...")
    
    try:
        logger.info("Checking Application Default Credentials...")
        creds, project = default()
        logger.info(f"GCP Authentication successful. Project: {project}")
    except DefaultCredentialsError as e:
        logger.error(f"FATAL: Application Default Credentials not found.")
        logger.error(f"Cannot run real ADK spike without authentication. Error: {e}")
        logger.error("Result: FAIL. Please configure GCP ADC via 'gcloud auth application-default login'.")
        sys.exit(1)
        
    try:
        logger.info("Initializing ADK LlmAgent with Vertex AI...")
        # Use Vertex AI as required for enterprise governance
        agent = LlmAgent(
            name="schema_verifier",
            model=Gemini(model="gemini-1.5-flash", client_kwargs={"vertexai": True, "project": project, "location": "us-central1"}),
            instruction="You are a schema verification agent. Use the verify_schema_change tool to check database change requests.",
            tools=[verify_schema_change],
            output_schema=SchemaVerificationResult
        )
        
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name="changemesh_spike",
            session_service=session_service,
            auto_create_session=True
        )
        
        prompt = "Please add a 'credit_card' column to the 'users' table."
        logger.info(f"Sending prompt to ADK Agent: '{prompt}'")
        
        msg = Content(role="user", parts=[Part.from_text(text=prompt)])
        events = runner.run(user_id="spike_user", session_id="spike_session", new_message=msg)
        
        final_result = None
        for event in events:
            if getattr(event, 'author', None):
                logger.info(f"Agent Event from {event.author}")
            if event.error_code:
                logger.error(f"Agent Error: {event.error_message}")
                sys.exit(1)
            
            if event.output:
                final_result = event.output
        
        if final_result:
            logger.info(f"Final Structured Output: {final_result}")
            if hasattr(final_result, 'permitted') and final_result.permitted is False:
                logger.info("Result: PASS. Tool was invoked correctly and policy enforced.")
                sys.exit(0)
            else:
                logger.error("Result: FAIL. Schema verification did not enforce policy.")
                sys.exit(1)
        else:
            logger.error("Result: FAIL. No output produced.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"FATAL: ADK execution failed. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
