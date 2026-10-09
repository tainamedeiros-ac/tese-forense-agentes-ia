"""Agente AUTÔNOMO: o modelo decide quando buscar, quando ler páginas e quando parar.

O contraste com `agents/researcher_agent.py` é o ponto do arquivo:

    researcher_agent.py  ->  o fluxo é um `for` fixo no Python; o modelo só resume.
    autonomous_agent.py  ->  há um loop de "tool-calling": a cada rodada o modelo
                             OU pede pra chamar uma ferramenta OU entrega a resposta
                             final. Quem escolhe a próxima ação é o modelo.

O loop de decisão em `run` é literalmente o que bibliotecas como
LangChain/LangGraph (`create_react_agent`, `AgentExecutor`) fazem por baixo dos
panos. Aqui ele está escrito à mão, com a lib `ollama`, porque (a) é mais
transparente para estudar e (b) o `langchain-core` não carrega neste ambiente
(a DLL nativa de `uuid_utils` está bloqueada pelo Smart App Control do Windows).

Como o modelo local é pequeno (qwen2.5:7b) e às vezes se recusa a usar as
ferramentas, há dois "empurrões" determinísticos: um lembrete (`GROUNDING_NUDGE`)
e, se ainda assim ele não ler nada, o código lê as primeiras páginas por ele
(`_auto_read`). O modelo continua escolhendo as consultas e escrevendo a síntese.

Segurança: o filtro de conteúdo para menores continua sendo uma checagem
determinística ANTES do loop — não delegamos isso ao agente.
"""
from __future__ import annotations

import re

import ollama
from rich.console import Console

from agents import audit
from llm_client import DEFAULT_MODEL
from tools.agent_tools import SourceTracker, build_toolset

AGENT_VERSION = "2.0.0"
ENGINE_NAME = "Agente autônomo (tool-calling via lib ollama)"
MAX_STEPS = 12

SYSTEM_PROMPT = (
    "Você é um agente de pesquisa autônomo. É OBRIGATÓRIO fundamentar a resposta em "
    "informação REAL da web. NUNCA responda a partir do seu conhecimento prévio.\n\n"
    "Ferramentas:\n"
    "- web_search(query): lista resultados da web.\n"
    "- read_page(url): devolve o texto de uma página.\n\n"
    "Fluxo obrigatório:\n"
    "1. Chame web_search (uma ou mais vezes; refine a consulta se preciso).\n"
    "2. Chame read_page em 2 a 4 páginas relevantes dos resultados.\n"
    "3. Só depois de ter lido as páginas, escreva a resposta final, sem chamar "
    "mais ferramentas.\n"
    "Se você escrever uma resposta sem ter chamado read_page, ela será rejeitada.\n\n"
    "Resposta final:\n"
    "- Inteiramente em português do Brasil (traduza trechos de outros idiomas).\n"
    "- Cite as fontes inline no padrão IEEE: o número entre colchetes ([1], [2]) "
    "logo após a informação, numerando na ordem em que você leu as páginas.\n"
    "- Não escreva uma lista de referências no fim; o sistema anexa isso sozinho."
)

GROUNDING_NUDGE = (
    "Você ainda não leu nenhuma página. NÃO responda de memória. "
    "Chame web_search agora e depois read_page em 2 ou 3 resultados antes de responder."
)
MAX_NUDGES = 2

FORCE_FINAL_PROMPT = (
    "Pare de usar ferramentas. Escreva agora a resposta final em português do "
    "Brasil, com citações [n], usando apenas o que você já coletou."
)


class AutonomousResearcherAgent:
    """Mesma interface pública de `ResearcherAgent`: instanciar e chamar `run(query)`."""

    def __init__(
        self,
        user_name: str,
        user_age: int,
        console: Console | None = None,
        model: str = DEFAULT_MODEL,
        max_steps: int = MAX_STEPS,
    ):
        self.user_name = user_name
        self.user_age = user_age
        self.console = console or Console()
        self.model = model
        self.max_steps = max_steps

    def run(self, query: str) -> str:
        if self.user_age < 18:
            self.console.print("[dim]Verificando se o tema é apropriado para a sua idade...[/dim]")
            if not self._is_appropriate_for_minor(query):
                message = "Esse tema não pode ser pesquisado por menores de idade nesta ferramenta."
                self.console.print(f"\n[bold red]{message}[/bold red]")
                audit.log_history(
                    self.user_name, self.user_age, query,
                    "BLOQUEADO", "conteúdo impróprio para menor de idade",
                )
                return message

        tracker = SourceTracker()
        tools = build_toolset(self.console, tracker)
        tools_by_name = {fn.__name__: fn for fn in tools}

        messages: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        self.console.print(f"\n[bold cyan]Objetivo do agente:[/bold cyan] {query}")
        self.console.print("[dim]O modelo decide os próximos passos (ferramentas em magenta):[/dim]\n")

        final_text = ""
        steps_used = 0
        nudges_used = 0
        auto_read_done = False
        for step in range(1, self.max_steps + 1):
            steps_used = step
            response = ollama.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                options={"temperature": 0},
            )
            message = response.message
            messages.append(message)

            if not message.tool_calls:
                # o modelo tentou concluir: só aceitamos se ele fundamentou a resposta
                if not tracker.visited:
                    if nudges_used < MAX_NUDGES:
                        nudges_used += 1
                        self.console.print(
                            "  [yellow]o agente tentou responder de memória; exigindo pesquisa[/yellow]"
                        )
                        messages.append({"role": "user", "content": GROUNDING_NUDGE})
                        continue
                    if not auto_read_done and tracker.result_urls:
                        # backstop: o modelo insiste em não ler; o código lê por ele
                        auto_read_done = True
                        self._auto_read(tools_by_name["read_page"], tracker, messages)
                        continue
                final_text = (message.content or "").strip()
                self.console.print(f"\n[dim]O agente concluiu após {step} rodada(s) de decisão.[/dim]")
                break

            for call in message.tool_calls:
                name = call.function.name
                args = dict(call.function.arguments or {})
                fn = tools_by_name.get(name)
                if fn is None:
                    result = f"Ferramenta desconhecida: {name}. Use web_search ou read_page."
                else:
                    try:
                        result = fn(**args)
                    except Exception as exc:  # devolve o erro pro modelo em vez de derrubar o agente
                        result = f"Erro ao executar {name}: {exc}"
                messages.append({"role": "tool", "tool_name": name, "content": str(result)})
        else:
            self.console.print(
                f"[yellow]Limite de {self.max_steps} rodadas atingido; forçando resposta final.[/yellow]"
            )

        if not final_text:
            final_text = self._force_final_answer(messages)

        return self._finish(query, final_text, tracker, steps_used)

    # ------------------------------------------------------------------ helpers

    def _auto_read(self, read_page, tracker: SourceTracker, messages: list, n: int = 3) -> None:
        self.console.print(
            f"  [yellow]o agente não abriu nenhuma página; lendo as {n} primeiras "
            "automaticamente[/yellow]"
        )
        # prioriza páginas HTML: sem trafilatura/lxml não conseguimos ler PDF
        ordered = sorted(tracker.result_urls, key=lambda u: u.lower().endswith(".pdf"))
        for url in ordered[:n]:
            out = read_page(url)
            messages.append({"role": "tool", "tool_name": "read_page", "content": str(out)})
        messages.append({
            "role": "user",
            "content": "Agora você tem o texto das páginas acima. Escreva a resposta "
                       "final em português do Brasil, com citações [n] na ordem das páginas.",
        })

    def _is_appropriate_for_minor(self, query: str) -> bool:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": audit.MODERATION_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            options={"temperature": 0},
        )
        return (response.message.content or "").strip().upper().startswith("SIM")

    def _force_final_answer(self, messages: list) -> str:
        messages.append({"role": "user", "content": FORCE_FINAL_PROMPT})
        response = ollama.chat(model=self.model, messages=messages, options={"temperature": 0})
        return (response.message.content or "").strip() or "(o agente não produziu uma resposta)"

    @staticmethod
    def _strip_trailing_references(text: str) -> str:
        """Remove uma seção 'Referências/Fontes' que o modelo insista em escrever no fim.

        O relatório já anexa referências IEEE montadas em Python (a partir das
        páginas realmente lidas); a lista do modelo costuma ter URLs inventadas.
        """
        heading = re.compile(
            r"\n[#*\s]*(refer[êe]ncias?|fontes?|bibliografia|references?)\s*:?\s*\n",
            re.IGNORECASE,
        )
        matches = list(heading.finditer(text))
        # só corta se já houver conteúdo de sobra antes do cabeçalho (evita cortar
        # uma menção a "referências" que faça parte da explicação)
        if matches and matches[-1].start() >= 200:
            text = text[: matches[-1].start()].rstrip()

        # também remove uma "bibliografia" final sem cabeçalho: um bloco de 2+
        # linhas consecutivas começando com [n] no fim do texto
        trailing = re.search(r"(?:\n[ \t]*\[\d+\][^\n]*){2,}\s*$", text)
        if trailing and trailing.start() >= 200:
            text = text[: trailing.start()].rstrip()
        return text

    def _finish(self, query: str, final_text: str, tracker: SourceTracker, steps_used: int) -> str:
        final_text = self._strip_trailing_references(final_text)
        sources = tracker.sources()
        references = (
            audit.build_references(sources)
            if sources
            else "(o agente não leu nenhuma página com read_page)"
        )
        header = audit.build_audit_header(
            self.user_name,
            self.user_age,
            query,
            engine_name=ENGINE_NAME,
            model=self.model,
            agent_version=AGENT_VERSION,
            extra_lines=(
                f"Rodadas de decisão do modelo: {steps_used}",
                f"Buscas feitas pelo agente: {len(tracker.searches)}",
                f"Páginas efetivamente lidas: {len(sources)}",
            ),
        )
        full_report = f"{header}\n{final_text}\n\nReferências\n{references}"

        self.console.rule("[bold]Resposta do agente[/bold]")
        self.console.print(final_text)
        self.console.rule("[bold]Referências (IEEE)[/bold]")
        self.console.print(references)

        saved_path = audit.save_to_file(query, full_report)
        self.console.print(f"\n[dim]Resumo salvo em:[/dim] {saved_path}")
        audit.log_history(
            self.user_name, self.user_age, query,
            "CONCLUIDO",
            f"arquivo: {saved_path.name} | modo: autônomo | rodadas: {steps_used}",
        )
        return full_report
