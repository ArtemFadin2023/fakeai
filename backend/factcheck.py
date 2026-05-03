import re
import os
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "google/gemma-4-26b-a4b-it:free"

def ai_request(system_prompt, user_message):
    if not API_KEY:
        return None
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}], "temperature": 0.7, "max_tokens": 1000},
            timeout=60
        )
        data = response.json()
        return data["choices"][0]["message"]["content"] if data.get("choices") else None
    except Exception as e:
        print(f"OpenRouter API Error: {e}")
        return None

def build_chat(text):
    result = ai_request("Ты полезный AI ассистент. Отвечай кратко и дружелюбно на русском языке.", text[:3000])
    return result or "⚠️ Сервис временно недоступен"

def build_smart(text):
    result = ai_request("Ты умный аналитик. Дай развернутый ответ с логическим разбором. Ответ на русском языке.", text[:3000])
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
    result = ai_request("Ты эксперт по проверке фактов. Верни: VERDICT: [ФЕЙК/ПРАВДА/НЕЯСНО], CONFIDENCE: [0-100]%, EXPLANATION: [объяснение]", text[:3000])
    if not result:
        return "⚠️ Сервис временно недоступен"
    verdict, confidence, explanation = parse_verdict(result)
    return f"{verdict}\n\n📊 Уверенность: {confidence}%\n\n💬 {explanation}"