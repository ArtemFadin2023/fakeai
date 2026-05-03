import re
import os
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("ANTHROPIC_API_KEY")

def ai_request(system_prompt, user_message):
    if not API_KEY:
        return None
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": API_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"},
            json={"model": "claude-3-5-haiku-20241022", "max_tokens": 500, "system": system_prompt, "messages": [{"role": "user", "content": user_message}]},
            timeout=30
        )
        data = response.json()
        return data["content"][0]["text"] if data.get("content") else None
    except Exception as e:
        print(f"Claude API Error: {e}")
        return None

def build_chat(text):
    result = ai_request("Ты полезный AI ассистент. Отвечай кратко и дружелюбно на русском языке.", text[:2000])
    return result or "⚠️ Сервис временно недоступен"

def build_smart(text):
    result = ai_request("Ты умный аналитик. Дай развернутый ответ с логическим разбором. Ответ на русском языке.", text[:2000])
    return result or "⚠️ Сервис временно недоступен"

def parse_verdict(text):
    verdict = "❓ НЕЯСНО"
    confidence = 50
    if "ФЕЙК" in text.upper():
        verdict = "🚨 ФЕЙК"
    elif "ПРАВДА" in text.upper():
        verdict = "✅ ПРАВДА"
    match = re.search(r'(\d+)%', text)
    if match:
        confidence = int(match.group(1))
    return verdict, confidence, text

def build_news(text):
    result = ai_request("Ты эксперт по проверке фактов. Верни: VERDICT: [ФЕЙК/ПРАВДА/НЕЯСНО], CONFIDENCE: [0-100]%, EXPLANATION: [объяснение]", text[:2000])
    if not result:
        return "⚠️ Сервис временно недоступен"
    verdict, confidence, explanation = parse_verdict(result)
    return f"{verdict}\n\n📊 Уверенность: {confidence}%\n\n💬 {explanation}"