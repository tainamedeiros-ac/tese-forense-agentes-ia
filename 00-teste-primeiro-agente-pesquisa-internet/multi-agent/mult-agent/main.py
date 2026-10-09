"""Console para interagir com os agentes de pesquisa."""
from collections.abc import Callable

from rich.console import Console

from agents.autonomous_agent import AutonomousResearcherAgent
from agents.researcher_agent import ResearcherAgent


def _ask_mode(console: Console) -> str:
    console.print("\n[bold]Escolha o modo de execução:[/bold]")
    console.print("  1 - Pipeline determinístico (o código Python decide cada passo)")
    console.print("  2 - Agente autônomo (o modelo decide quando buscar, ler e parar)")
    while True:
        choice = console.input("[bold cyan]Opção [1/2] (padrão 1): [/bold cyan]").strip()
        if choice in ("", "1"):
            return "deterministico"
        if choice == "2":
            return "autonomo"
        console.print("[red]Digite 1 ou 2.[/red]")


def _ask_engine(console: Console) -> tuple[Callable[..., str], str]:
    console.print("\n[bold]Motor para falar com o modelo:[/bold]")
    console.print("  1 - Ollama (chamada direta)")
    console.print("  2 - LangChain (usa Ollama por baixo via langchain-ollama)")
    while True:
        choice = console.input("[bold cyan]Opção [1/2] (padrão 1): [/bold cyan]").strip()
        if choice in ("", "1"):
            from llm_client import ask as ollama_ask
            return ollama_ask, "Ollama (chamada direta)"
        if choice == "2":
            try:
                from langchain_client import ask as langchain_ask
            except Exception as exc:  # p.ex. uuid_utils bloqueado por política do Windows
                console.print(
                    f"[red]LangChain indisponível neste ambiente "
                    f"({exc.__class__.__name__}). Usando Ollama direto.[/red]"
                )
                from llm_client import ask as ollama_ask
                return ollama_ask, "Ollama (chamada direta)"
            return langchain_ask, "LangChain (via langchain-ollama)"
        console.print("[red]Digite 1 ou 2.[/red]")


def _ask_age(console: Console) -> int:
    while True:
        raw = console.input("[bold cyan]Sua idade: [/bold cyan]").strip()
        try:
            age = int(raw)
        except ValueError:
            console.print("[red]Digite um número válido.[/red]")
            continue
        if age < 0 or age > 120:
            console.print("[red]Digite uma idade válida.[/red]")
            continue
        return age


def _build_agent(mode: str, name: str, age: int, console: Console):
    if mode == "autonomo":
        return AutonomousResearcherAgent(user_name=name, user_age=age, console=console)

    ask_fn, engine_name = _ask_engine(console)
    return ResearcherAgent(
        user_name=name,
        user_age=age,
        console=console,
        ask_fn=ask_fn,
        engine_name=engine_name,
    )


def main() -> None:
    console = Console()
    console.print("[bold]Agente de pesquisa[/bold] (Ctrl+C para sair)")

    try:
        mode = _ask_mode(console)
        name = console.input("[bold cyan]Seu nome: [/bold cyan]").strip() or "Anônimo"
        age = _ask_age(console)
        agent = _build_agent(mode, name, age, console)
    except (KeyboardInterrupt, EOFError):
        console.print("\nAté mais!")
        return

    while True:
        try:
            query = console.input("\n[bold cyan]O que você quer pesquisar? [/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\nAté mais!")
            break

        if not query.strip():
            continue

        agent.run(query)


if __name__ == "__main__":
    main()
