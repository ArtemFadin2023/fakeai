import re
import os
import requests
from dotenv import load_dotenv

# =========================
# ENV
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "mistralai/mistral-7b-instruct:free"
TIMEOUT = 15

# =========================
# AI CALLS
# =========================

def ai_request(system_prompt, user_message):
    """Универсальный AI запрос"""
    if not API_KEY:
        return None

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.7,
                "max_tokens": 1000
            },
            timeout=TIMEOUT
        )

        data = response.json()

        if "choices" not in data or not data["choices"]:
            return None

        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

# =========================
# ANALYSIS FUNCTIONS
# =========================

def build_chat(text):
    """Обычный чат режим"""
    result = ai_request(
        "Ты полезный AI ассистент. Отвечай кратко, понятно и дружелюбно на русском языке.",
        text[:3000]
    )
    
    if not result:
        return "⚠️ Сервис временно недоступен"
    
    return result

def build_smart(text):
    """Умный аналитический режим"""
    result = ai_request(
        """Ты умный аналитик и эксперт.
        
Требования:
- Дай развернутый ответ с логическим разбором
- Объясняй глубже, приводи примеры и контекст
- Анализируй разные стороны вопроса
- Цитируй источники если возможно
- Ответ на русском языке""",
        text[:3000]
    )
    
    if not result:
        return "⚠️ Сервис временно недоступен"
    
    return result

def parse_verdict(result):
    """Парсить вердикт из ответа"""
    verdict = "🟡 НЕЯСНО"
    confidence = 50
    explanation = "Нет данных для анализа"

    try:
        text = result.upper()

        if "ФЕЙК" in text or "FALSE" in text or "ЛОЖЬ" in text:
            verdict = "🚨 ФЕЙК"
        elif "ПРАВДА" in text or "TRUE" in text or "ИСТИНА" in text:
            verdict = "🟢 ПРАВДА"
        elif "PARTIALLY" in text or "ЧАСТИЧН" in text:
            verdict = "🟡 ЧАСТИЧНО ВЕРНО"

        # Найти процент уверенности
        nums = re.findall(r'\b(\d{1,3})\s*%', result)
        if nums:
            confidence = min(int(nums[0]), 100)
        
        # Найти объяснение
        patterns = [
            r"ОБЪЯСНЕНИЕ[:\s]+([^\n]+)",
            r"EXPLANATION[:\s]+([^\n]+)",
            r"Вывод[:\s]+([^\n]+)",
            r"Заключение[:\s]+([^\n]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                explanation = match.group(1).strip()
                break

    except Exception as e:
        print(f"Parse error: {e}")

    return verdict, confidence, explanation

def build_news(text):
    """Режим проверки новостей и фактов"""
    check_prompt = """Ты эксперт по проверке фактов и дезинформации.

Проанализируй текст и верни:

VERDICT: [ФЕЙК / ПРАВДА / НЕЯСНО]
CONFIDENCE: [0-100]%
EXPLANATION: [краткое объяснение]

Критерии:
- ФЕЙК: явно ложная информация, противоречит проверенным фактам
- ПРАВДА: подтверждено источниками, логично и верно
- НЕЯСНО: недостаточно данных, спорно, требует уточнения

Будь критичен к:
- Статистике без источников
- Цитатам без контекста
- Манипуляциям с фактами
- Эмоциональным манипуляциям
"""

    result = ai_request(check_prompt, text[:3000])

    if not result:
        return "⚠️ Сервис временно недоступен"

    verdict, confidence, explanation = parse_verdict(result)

    return f"""{verdict}

📊 Уверенность: {confidence}%

💬 {explanation}"""

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    # Test
    test_text = "Земля плоская"
    print("Testing news mode...")
    print(build_news(test_text))
