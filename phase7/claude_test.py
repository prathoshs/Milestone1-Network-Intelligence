import os
from dotenv import load_dotenv
from anthropic import Anthropic
load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY") 
if not api_key:
    raise RuntimeError("ANTHROPIC_API_KEY was not found.")
client = Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1000,
    messages=[
        {
            "role": "user",
            "content": "In one sentence, explain what a telecom network hotspot is."
        }
    ],
)
print(response.content[0].text)