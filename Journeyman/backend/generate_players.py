import anthropic
import json
import os
from dotenv import load_dotenv
import re

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def randomPlayer():
    message = client.messages.create(
        model = "claude-sonnet-4-6",
        max_tokens = 1024,
        messages = [
            {
                "role": "user",
                "content": """Give me a random active NBA player who has played for at least 2 teams.
                Pick a truly random player — not just popular stars, include role players and bench players too.
                To ensure randomness, first pick a random letter of the alphabet, then pick a player whose 
                last name starts with that letter.
                Return ONLY a JSON object in this exact format, nothing else:
                {
                    "name": "Player Name",
                    "teams": ["first team", "second team", "third team"]
                } 
                Teams should be in chronological order, lowercase, and use full team names like 
                'los angeles lakers' not 'lakers'. Only include teams from the NBA, not g-league."""
            }
        ]
    )

    raw = message.content[0].text
    matches = re.findall(r'\{[^{}]*\}', raw, re.DOTALL)
    clean = matches[-1]
    data = json.loads(clean)
    return data["name"], data["teams"]