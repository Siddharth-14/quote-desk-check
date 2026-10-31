"""Tiny local-Ollama client. No API key, no network beyond localhost."""
import json
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b-instruct"


def chat(messages, temperature=0.0, seed=7, fmt=None, num_predict=900, model=MODEL):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "seed": seed, "num_ctx": 4096, "num_predict": num_predict},
    }
    if fmt is not None:
        payload["format"] = fmt
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]["content"]
