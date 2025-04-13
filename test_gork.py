import os
import requests

XAI_API_KEY = "xai-t1692FGhO1Eotjxz4rsXHz9AahCWW3v5Pghk9BYt4crHCL0UwFjdngGsEvXlI15qF9ZDPepXgnfhFNm6"
headers = {
    "Authorization": f"Bearer {XAI_API_KEY}",
    "Content-Type": "application/json"
}

data = {
    "model": "grok-2-latest",
    "messages": [
        {"role": "system", "content": "You are Grok, a chatbot inspired by the Hitchhiker's Guide to the Galaxy."},
        {"role": "user", "content": "What is the meaning of life, the universe, and everything?"}
    ]
}

response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data)

if response.status_code == 200:
    completion = response.json()
    print(completion)
    # print(completion['choices'][0]['message']['content'])
else:
    print(f"Error: {response.status_code}, {response.text}")
