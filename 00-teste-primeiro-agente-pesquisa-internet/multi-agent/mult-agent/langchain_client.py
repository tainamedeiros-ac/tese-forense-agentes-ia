"""Wrapper para conversar com um modelo local via Ollama, usando LangChain."""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

DEFAULT_MODEL = "qwen2.5:7b"


def ask(prompt: str, system: str | None = None, model: str = DEFAULT_MODEL) -> str:
    """Envia um prompt ao modelo local (via LangChain) e retorna a resposta em texto."""
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    llm = ChatOllama(model=model)
    response = llm.invoke(messages)
    return response.content
