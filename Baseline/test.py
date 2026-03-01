import os, requests, json

api_key = os.environ["FORGE_API_KEY"].strip()
base_url = "https://api.forge.tensorblock.co/v1"

payload = {
    "model": "tensorblock/gpt-4.1-mini",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 20,
}

resp = requests.post(
    f"{base_url}/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    data=json.dumps(payload),
    timeout=30,
)

data = resp.json()
print("status:", resp.status_code)

usage = data.get("usage")
print("usage:", usage)  # 这里就是 token 消耗

if usage:
    print("prompt_tokens:", usage.get("prompt_tokens"))
    print("completion_tokens:", usage.get("completion_tokens"))
    print("total_tokens:", usage.get("total_tokens"))