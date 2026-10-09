"""Wrapper simples para conversar com um modelo local via Ollama."""
import ollama

DEFAULT_MODEL = "qwen2.5:7b"


def ask(prompt: str, system: str | None = None, model: str = DEFAULT_MODEL) -> str:
    """Envia um prompt ao modelo local e retorna a resposta em texto."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = ollama.chat(model=model, messages=messages)
    return response["message"]["content"]
