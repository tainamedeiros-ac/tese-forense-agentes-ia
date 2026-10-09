"""Agente generalista: pesquisa na web, lê os sites e resume o que encontrou.

Este é o pipeline DETERMINÍSTICO: o fluxo (buscar -> ler N páginas -> resumir cada
uma -> sintetizar) é fixo, escrito em `if`/`for` aqui no Python. O modelo só é
chamado para tarefas pontuais (moderar, resumir, sintetizar) e nunca decide o
próximo passo. Para a versão em que o modelo dirige o fluxo, veja
`agents/autonomous_agent.py`.
"""
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console

from agents import audit
from llm_client import DEFAULT_MODEL, ask
from tools.scraper import fetch_page_text
from tools.search import search_web

AGENT_VERSION = "1.1.0"
ENGINE_NAME_DEFAULT = "Ollama (chamada direta)"

SUMMARY_SYSTEM_PROMPT = (
    "Você é um assistente de pesquisa. Resuma o texto fornecido de forma "
    "objetiva, destacando os pontos mais relevantes. "
    "Se o texto parecer quebrado, incompleto ou não relacionado ao tema, diga isso. "
    "IMPORTANTE: responda inteiramente em português do Brasil, mesmo que o texto "
    "original esteja em outro idioma (inglês, espanhol, etc.). Traduza qualquer "
    "citação ou trecho necessário — não copie frases no idioma original."
)

FINAL_SYSTEM_PROMPT = (
    "Você é um assistente de pesquisa. Você recebeu resumos de várias fontes "
    "numeradas sobre o mesmo tema. Produza uma síntese única e objetiva, "
    "combinando os pontos em comum e destacando divergências "
    "relevantes entre as fontes. Sempre que usar uma informação de uma fonte, "
    "cite o número dela entre colchetes (ex.: [1], [2]) logo após a informação. "
    "Não inclua uma lista de referências no final do seu texto — apenas use as "
    "citações numéricas ao longo do texto, no padrão IEEE. "
    "IMPORTANTE: responda inteiramente em português do Brasil, mesmo que os "
    "resumos recebidos contenham trechos em outro idioma — traduza tudo."
)

@dataclass
class PageSummary:
    title: str
    url: str
    summary: str


class ResearcherAgent:
    """Agente único que pesquisa um tema na web e resume o conteúdo encontrado."""

    def __init__(
        self,
        user_name: str,
        user_age: int,
        console: Console | None = None,
        max_results: int = 3,
        search_pool_size: int | None = None,
        ask_fn: Callable[..., str] = ask,
        engine_name: str = "Ollama (chamada direta)",
    ):
        self.console = console or Console()
        self.max_results = max_results
        # busca uma folga de resultados extras pra ter de onde tentar a próxima
        # página quando alguma falha ao abrir/ler
        self.search_pool_size = search_pool_size or max_results * 4
        self.user_name = user_name
        self.user_age = user_age
        self.ask_fn = ask_fn
        self.engine_name = engine_name

    def run(self, query: str) -> str:
        if self.user_age < 18:
            self.console.print("[dim]Verificando se o tema é apropriado para a sua idade...[/dim]")
            if not self._is_appropriate_for_minor(query):
                message = "Esse tema não pode ser pesquisado por menores de idade nesta ferramenta."
                self.console.print(f"\n[bold red]{message}[/bold red]")
                self._log_history(query, "BLOQUEADO", "conteúdo impróprio para menor de idade")
                return message

        self.console.print(f"\n[bold cyan]Pesquisando:[/bold cyan] {query}")
        results = search_web(query, max_results=self.search_pool_size)

        if not results:
            self._log_history(query, "SEM_RESULTADOS")
            return "Não encontrei nenhum resultado para essa pesquisa."

        page_summaries: list[PageSummary] = []
        for result in results:
            if len(page_summaries) >= self.max_results:
                break

            self.console.print(
                f"[bold yellow]({len(page_summaries) + 1}/{self.max_results}) Abrindo:[/bold yellow] {result.url}"
            )
            text = fetch_page_text(result.url)

            if not text:
                self.console.print("  [red]Não consegui ler essa página, tentando a próxima...[/red]")
                continue

            self.console.print("  [dim]Resumindo conteúdo com o modelo local...[/dim]")
            summary = self.ask_fn(prompt=text, system=SUMMARY_SYSTEM_PROMPT)
            page_summaries.append(PageSummary(result.title, result.url, summary))

        if not page_summaries:
            self._log_history(query, "FALHA_LEITURA", "nenhuma página pôde ser lida")
            return "Não consegui ler nenhuma das páginas encontradas."

        if len(page_summaries) < self.max_results:
            self.console.print(
                f"\n[yellow]Só consegui ler {len(page_summaries)} de {self.max_results} páginas "
                "desejadas (esgotei os resultados da busca).[/yellow]"
            )

        self.console.print("\n[bold green]Consolidando resumo final...[/bold green]")
        final_summary = self._build_final_summary(query, page_summaries)
        references = self._build_references(page_summaries)
        audit_header = self._build_audit_header(query)
        full_report = f"{audit_header}\n{final_summary}\n\nReferências\n{references}"

        self._print_report(page_summaries, final_summary, references)

        saved_path = self._save_to_file(query, full_report)
        self.console.print(f"\n[dim]Resumo salvo em:[/dim] {saved_path}")

        self._log_history(query, "CONCLUIDO", f"arquivo: {saved_path.name}")

        return full_report

    def _is_appropriate_for_minor(self, query: str) -> bool:
        answer = self.ask_fn(prompt=query, system=audit.MODERATION_SYSTEM_PROMPT)
        return answer.strip().upper().startswith("SIM")

    def _log_history(self, query: str, status: str, detail: str = "") -> None:
        audit.log_history(self.user_name, self.user_age, query, status, detail)

    def _build_audit_header(self, query: str) -> str:
        return audit.build_audit_header(
            self.user_name,
            self.user_age,
            query,
            engine_name=self.engine_name,
            model=DEFAULT_MODEL,
            agent_version=AGENT_VERSION,
        )

    def _build_final_summary(self, query: str, page_summaries: list[PageSummary]) -> str:
        joined = "\n\n".join(
            f"[{i}] Fonte: {p.title} ({p.url})\nResumo: {p.summary}"
            for i, p in enumerate(page_summaries, start=1)
        )
        prompt = f"Tema pesquisado: {query}\n\nResumos individuais das fontes:\n\n{joined}"
        return self.ask_fn(prompt=prompt, system=FINAL_SYSTEM_PROMPT)

    def _build_references(self, page_summaries: list[PageSummary]) -> str:
        return audit.build_references((p.title, p.url) for p in page_summaries)

    def _print_report(
        self, page_summaries: list[PageSummary], final_summary: str, references: str
    ) -> None:
        self.console.rule("[bold]Resumo por fonte[/bold]")
        for i, p in enumerate(page_summaries, start=1):
            self.console.print(f"\n[bold][{i}] {p.title}[/bold]\n[link]{p.url}[/link]")
            self.console.print(p.summary)

        self.console.rule("[bold]Síntese final[/bold]")
        self.console.print(final_summary)

        self.console.rule("[bold]Referências (IEEE)[/bold]")
        self.console.print(references)

    def _save_to_file(self, query: str, content: str):
        return audit.save_to_file(query, content)
