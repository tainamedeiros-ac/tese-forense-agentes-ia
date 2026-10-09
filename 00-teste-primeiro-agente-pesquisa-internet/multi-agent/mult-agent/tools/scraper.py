"""Abre uma URL e extrai o conteúdo textual principal da página.

Duas estratégias, escolhidas em runtime:

* `trafilatura` (melhor qualidade) — usada se conseguir ser importada.
* Extrator da biblioteca padrão (`html.parser` + `httpx`) — fallback puro-Python,
  sem dependências nativas. Existe porque o Smart App Control do Windows pode
  bloquear a DLL nativa do `lxml` (dependência do trafilatura); nesse caso o
  import acima falha e caímos aqui.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

MAX_CHARS = 8000  # limite pra não estourar o contexto do modelo local
_TIMEOUT = 20.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

try:
    import trafilatura
except Exception:  # lxml bloqueado pelo Smart App Control, ou trafilatura ausente
    trafilatura = None


def fetch_page_text(url: str) -> str | None:
    """Baixa a página e retorna o texto principal (sem menus/propaganda).

    Retorna None se não conseguir baixar ou extrair nada.
    """
    if trafilatura is not None:
        text = _extract_with_trafilatura(url)
        if text:
            return text[:MAX_CHARS]
        # se o trafilatura não achou nada, ainda tentamos o fallback abaixo

    html = _download(url)
    if not html:
        return None
    text = _extract_with_stdlib(html)
    return text[:MAX_CHARS] if text else None


def _extract_with_trafilatura(url: str) -> str | None:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded, include_comments=False, include_tables=False)


def _download(url: str) -> str | None:
    try:
        response = httpx.get(
            url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return response.text


_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "aside", "form"}
_BLOCK_TAGS = {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # colapsa espaços dentro de cada linha, remove linhas vazias em excesso
        lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(ln for ln in lines if ln)).strip()


def _extract_with_stdlib(html: str) -> str | None:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return None
    text = parser.get_text()
    return text or None
