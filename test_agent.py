import asyncio
from dotenv import load_dotenv
load_dotenv()

from google.adk.runners import InMemoryRunner
from google.genai import types
from app.agent import app

async def main():
    runner = InMemoryRunner(app=app)
    user_id = "test_user"
    session_id = "test_session"

    await runner.session_service.create_session(
        app_name=app.name,
        user_id=user_id,
        session_id=session_id
    )

    query = "Can you generate a workout illustration image for a dumbbell biceps curl?"
    print(f"\n--- User Query: '{query}' ---")

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)

    print("\n--- Done ---")

if __name__ == "__main__":
    asyncio.run(main())
