"""Peças de auditoria/relatório compartilhadas pelos agentes.

Tanto o pipeline determinístico (`researcher_agent.py`) quanto o agente autônomo
(`autonomous_agent.py`) produzem o mesmo tipo de saída: um `.txt` com cabeçalho de
auditoria + referências no padrão IEEE, e uma linha no log de histórico. Esse código
mora aqui pra não ser duplicado nos dois.
"""
from __future__ import annotations

import re
import webbrowser
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import winreg
except ImportError:  # não estamos no Windows
    winreg = None

SEARCH_ENGINE = "DuckDuckGo (via biblioteca ddgs)"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "resumos"
HISTORY_LOG_PATH = OUTPUT_DIR / "historico_auditoria.log"

MODERATION_SYSTEM_PROMPT = (
    "Você é um filtro de segurança de conteúdo para menores de idade (menos de "
    "18 anos). Dado um tema de pesquisa, responda apenas com a palavra SIM se o "
    "tema for apropriado para um menor pesquisar, ou apenas com a palavra NAO se "
    "o tema envolver conteúdo adulto/sexual, violência explícita, drogas, "
    "automutilação, jogos de azar, armas ou qualquer outro assunto impróprio "
    "para menores. Responda somente com uma única palavra: SIM ou NAO."
)


def slugify(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")[:50] or "pesquisa"


def detect_default_browser() -> str:
    # Best-effort: os agentes não abrem um navegador de verdade (as páginas são
    # baixadas via HTTP em tools/scraper.py), então isto reporta apenas o
    # navegador padrão configurado no sistema operacional, como dado de auditoria.
    # webbrowser.get().name vem sempre vazio no Windows (limitação conhecida
    # da classe WindowsDefault da stdlib), então lemos o registro primeiro.
    if winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
            ) as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id) as key:
                display_name = winreg.QueryValueEx(key, None)[0]
            return display_name.removesuffix(" HTML Document")
        except OSError:
            pass

    try:
        return webbrowser.get().name or "não detectado"
    except webbrowser.Error:
        return "não detectado"


def log_history(user_name: str, user_age: int, query: str, status: str, detail: str = "") -> None:
    """Registra toda tentativa de pesquisa (inclusive bloqueadas) no log de auditoria."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    line = (
        f'[{timestamp}] {user_name} ({user_age} anos) | '
        f'Consulta: "{query}" | Status: {status}'
    )
    if detail:
        line += f" | {detail}"
    with HISTORY_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_audit_header(
    user_name: str,
    user_age: int,
    query: str,
    *,
    engine_name: str,
    model: str,
    agent_version: str,
    extra_lines: Iterable[str] = (),
) -> str:
    lines = [
        "===================== AUDITORIA =====================",
        f"Usuário: {user_name} ({user_age} anos)",
        f"Pesquisa: {query}",
        f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Navegador padrão do sistema: {detect_default_browser()}",
        f"Mecanismo de busca: {SEARCH_ENGINE}",
        f"Modelo LLM: {model}",
        f"Motor de execução: {engine_name}",
        f"Versão do agente: {agent_version}",
        f"Histórico completo de auditoria: {HISTORY_LOG_PATH.name}",
        *extra_lines,
        "======================================================",
    ]
    return "\n".join(lines)


def build_references(sources: Iterable[tuple[str, str]]) -> str:
    """Monta a lista de referências no padrão IEEE a partir de pares (título, url).

    Feito em Python puro (sem LLM) pra garantir que URL e título fiquem exatos.
    """
    access_date = datetime.now().strftime("%d %b. %Y")
    return "\n".join(
        f'[{i}] "{title}," {urlparse(url).netloc or url}. [Online]. '
        f"Disponível em: {url}. [Acesso em: {access_date}]."
        for i, (title, url) in enumerate(sources, start=1)
    )


def save_to_file(query: str, content: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{timestamp}_{slugify(query)}.txt"
    path.write_text(content, encoding="utf-8")
    return path
