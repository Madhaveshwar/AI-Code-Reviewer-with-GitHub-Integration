from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("GROQ_API_KEY is not configured.")

client = Groq(api_key=api_key)

print("Available Models:")

try:
    for model in client.models.list().data:
        print(model.id)
except Exception as e:
    print(f"Error listing models: {e}")
