import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

def verify_schema_change(table_name: str, column_name: str, action: str) -> str:
    print(f"\n[TOOL INVOKED] verify_schema_change(table_name='{table_name}', column_name='{column_name}', action='{action}')")
    if action.upper() == "DROP" and table_name.lower() == "users":
        return "DENIED: Dropping columns from the 'users' table requires human authority."
    return f"APPROVED: {action} on {table_name}.{column_name} is safe and reversible."

class ChangeAssessmentResult(BaseModel):
    is_approved: bool = Field(description="True if the change is approved, False otherwise.")
    policy_reason: str = Field(description="The exact reason returned by the policy check.")
    agent_confidence: str = Field(description="Agent's confidence level: HIGH, MEDIUM, or LOW.")

def run_agent(client: genai.Client, model_id: str, prompt: str):
    print(f"\n[>] USER PROMPT: {prompt}")
    
    # 1. Ask model to decide what to do (using the tool)
    tool_config = types.GenerateContentConfig(
        temperature=0.0,
        tools=[verify_schema_change],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="ANY",
                allowed_function_names=["verify_schema_change"]
            )
        )
    )
    
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=tool_config
    )
    
    tool_results = []
    
    # 2. Check if model wants to call a tool
    if response.function_calls:
        for function_call in response.function_calls:
            if function_call.name == "verify_schema_change":
                # Execute tool locally
                args = function_call.args
                result = verify_schema_change(
                    table_name=args.get("table_name", ""),
                    column_name=args.get("column_name", ""),
                    action=args.get("action", "")
                )
                tool_results.append(types.Part.from_function_response(
                    name="verify_schema_change",
                    response={"result": result}
                ))
    
    # 3. Request final structured output
    final_config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=ChangeAssessmentResult,
    )
    
    if tool_results:
        # Pass the tool result back to the model for final JSON generation
        history = [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
            types.Content(role="model", parts=response.parts),
            types.Content(role="user", parts=tool_results)
        ]
        final_response = client.models.generate_content(
            model=model_id,
            contents=history,
            config=final_config
        )
    else:
        # If it didn't call the tool, just get JSON directly
        final_response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=final_config
        )
        
    print("\n[<] AGENT FINAL STRUCTURED OUTPUT:")
    print(json.dumps(json.loads(final_response.text), indent=2))

def main():
    model_id = "gemini-3.6-flash"
    client = genai.Client(vertexai=True, location="global", project="project-af5e1c99-3bc4-424f-b53")
    
    print(f"[*] Starting manual ADK agent skeleton...")
    print(f"[*] Target Model: {model_id}")
    
    prompt_1 = "I want to ADD a new column called 'last_login' to the 'users' table. Assess this change."
    run_agent(client, model_id, prompt_1)
    
    prompt_2 = "Now I want to DROP the 'password_hash' column from the 'users' table. Assess this change."
    run_agent(client, model_id, prompt_2)

if __name__ == "__main__":
    main()
