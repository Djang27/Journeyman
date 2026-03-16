import anthropic
import json
import os
import re
import random
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def randomPlayer():
    letter = random.choice('abcdefghijklmnoprstw')
    
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""Give me a random active NBA player whose last name starts with the letter '{letter}' and who has played for at least 2 teams.
                Pick a truly random player — not just popular stars, include role players and bench players too.
                If the player returned to a team after playing elsewhere, include that as a separate entry.
                For example, LeBron James would be: ["cleveland cavaliers", "miami heat", "cleveland cavaliers", "los angeles lakers"]
                Return ONLY a JSON object in this exact format, nothing else:
                {{
                    "name": "Player Name",
                    "teams": ["first team", "second team", "third team"]
                }}
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