"""Ferramentas expostas ao MODELO no agente autônomo (tool-calling).

Diferença sutil mas central em relação a `tools/search.py` e `tools/scraper.py`:
lá as funções são chamadas pelo *código* do pipeline, numa ordem fixa. Aqui elas
são descritas para o *modelo*, que decide sozinho se/quando/quantas vezes chamar
cada uma. O que o modelo recebe é o docstring (vira a descrição da ferramenta) e a
assinatura tipada (vira o schema dos argumentos) — por isso os docstrings abaixo
são escritos "para o modelo ler".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console

from tools.scraper import fetch_page_text
from tools.search import search_web


@dataclass
class SourceTracker:
    """Registra o que o agente realmente fez, para auditoria e referências.

    O modelo pode "citar" fontes que nunca abriu; por isso as referências IEEE do
    relatório final são montadas só a partir das páginas que passaram de fato por
    `read_page` (ordem de leitura = ordem de numeração).
    """

    titles_by_url: dict[str, str] = field(default_factory=dict)
    result_urls: list[str] = field(default_factory=list)  # ordem em que apareceram nas buscas
    visited: list[str] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)

    def record_search(self, query: str, results) -> None:
        self.searches.append(query)
        for r in results:
            self.titles_by_url.setdefault(r.url, r.title)
            if r.url and r.url not in self.result_urls:
                self.result_urls.append(r.url)

    def record_visit(self, url: str) -> None:
        if url not in self.visited:
            self.visited.append(url)

    def sources(self) -> list[tuple[str, str]]:
        return [(self.titles_by_url.get(u, u), u) for u in self.visited]


def build_toolset(
    console: Console,
    tracker: SourceTracker,
    *,
    results_per_search: int = 5,
) -> list:
    """Cria as ferramentas como closures com acesso ao console e ao tracker.

    Retorna uma lista de funções puras (nome + docstring + type hints) — formato
    que a lib `ollama` converte sozinha para o schema de tool-calling.
    """

    def web_search(query: str) -> str:
        """Pesquisa na web e retorna resultados numerados (título, URL e trecho).

        Use para descobrir páginas sobre o tema. Pode ser chamada mais de uma vez,
        com consultas diferentes, para refinar a busca antes de ler as páginas.

        Args:
            query: O texto a pesquisar (em qualquer idioma).
        """
        console.print(f"  [magenta]web_search[/magenta]([cyan]{query!r}[/cyan])")
        results = search_web(query, max_results=results_per_search)
        tracker.record_search(query, results)
        if not results:
            return "Nenhum resultado. Tente reformular a consulta."
        return "\n".join(
            f"[{i}] {r.title}\n    URL: {r.url}\n    {r.snippet}"
            for i, r in enumerate(results, start=1)
        )

    def read_page(url: str) -> str:
        """Baixa uma página da web e devolve o texto principal (sem menus/anúncios).

        Use depois de web_search para ler o conteúdo de um resultado promissor.
        Leia de 2 a 4 páginas antes de escrever a resposta final.

        Args:
            url: O endereço http/https completo da página, copiado de um resultado.
        """
        console.print(f"  [magenta]read_page[/magenta]([cyan]{url!r}[/cyan])")
        text = fetch_page_text(url)
        if not text:
            return f"Falha ao ler {url}. Escolha outra página da lista de resultados."
        tracker.record_visit(url)
        return text

    return [web_search, read_page]
