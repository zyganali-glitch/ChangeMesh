import sys
import logging
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.models.google_llm import Gemini
from google.genai.types import Content, Part

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class SchemaVerificationResult(BaseModel):
    permitted: bool
    reason: str

def verify_schema_change(table_name: str, requested_columns: list[str]) -> SchemaVerificationResult:
    return SchemaVerificationResult(permitted=True, reason="No forbidden columns found.")

def main() -> None:
    agent = LlmAgent(
        name="schema_verifier",
        model=Gemini(
            model="gemini-3.5-flash",
            client_kwargs={
                "vertexai": True,
                "project": "test-project",
                "location": "us-central1",
            },
        ),
        instruction="You are a schema verification agent. Use the verify_schema_change tool to check database change requests.",
        tools=[verify_schema_change],
        output_schema=SchemaVerificationResult,
    )

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="changemesh_spike",
        session_service=session_service,
        auto_create_session=True,
    )

    msg = Content(
        role="user",
        parts=[Part.from_text(text="Please add a credit_card column to the users table.")],
    )
    try:
        events = runner.run(user_id="spike_user", session_id="spike_session", new_message=msg)
        for event in events:
            if event.error_code:
                logger.error(f"Agent Error: {event.error_message}")
                sys.exit(1)
            if event.output:
                print(event.output)
    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    main()
