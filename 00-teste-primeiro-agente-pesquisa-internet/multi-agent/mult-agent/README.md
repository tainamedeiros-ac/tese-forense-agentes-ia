# mult-agent

CLI de pesquisa que **busca na web, lê as páginas e resume com um LLM local**
(Ollama / `qwen2.5:7b`), salvando um relatório com cabeçalho de auditoria e
referências no padrão IEEE.

O projeto existe para estudar, na prática, a fronteira entre um **workflow**
(o código decide os passos) e um **agente autônomo** (o modelo decide os passos).
Por isso ele tem **dois modos**, escolhidos no menu inicial.

> Documentos irmãos:
> - [`ARQUITETURA.md`](ARQUITETURA.md) — Python para quem vem de Java, o que é um
>   agente, o que o Ollama faz na sua máquina.
> - [`AGENTE_AUTONOMO.md`](AGENTE_AUTONOMO.md) — detalhes do modo 2 e das
>   limitações do ambiente.

---

## 1. Visão geral

```mermaid
flowchart TD
    U(["Usuário no terminal"]) --> M["main.py<br/>CLI + menu de modo"]

    M -->|"modo 1"| RA["ResearcherAgent<br/>agents/researcher_agent.py<br/><i>fluxo fixo no código</i>"]
    M -->|"modo 2"| AA["AutonomousResearcherAgent<br/>agents/autonomous_agent.py<br/><i>o modelo dirige o loop</i>"]

    RA --> AUD["agents/audit.py<br/>auditoria · referências IEEE · log"]
    AA --> AUD

    RA --> LLM["llm_client.py / langchain_client.py"]
    AA --> OLL["lib ollama<br/>chat com tools"]

    RA --> SEARCH["tools/search.py<br/>search_web"]
    RA --> SCRAP["tools/scraper.py<br/>fetch_page_text"]

    AA --> AT["tools/agent_tools.py<br/>web_search · read_page<br/><i>descritas para o modelo</i>"]
    AT --> SEARCH
    AT --> SCRAP

    LLM --> OLLAMA[("Ollama<br/>localhost:11434<br/>qwen2.5:7b")]
    OLL --> OLLAMA
    SEARCH --> WEB[("Internet<br/>DuckDuckGo")]
    SCRAP --> WEB

    AUD --> FILES[["resumos/&lt;timestamp&gt;_&lt;tema&gt;.txt<br/>resumos/historico_auditoria.log"]]
```

Regra de dependência (como "camadas" numa arquitetura Java):
**`tools/` não conhece `agents/`; `agents/` conhece `tools/` e os clients;
`main.py` só conhece `agents/`.**

---

## 2. Estrutura de arquivos

| Arquivo | Papel | Camada (analogia Java) |
|---|---|---|
| `main.py` | CLI: pergunta modo → nome/idade → loop de perguntas | Controller |
| `agents/researcher_agent.py` | **Modo 1**: pipeline determinístico | Service |
| `agents/autonomous_agent.py` | **Modo 2**: loop de tool-calling | Service |
| `agents/audit.py` | Auditoria, referências IEEE, log — compartilhado | Service util |
| `llm_client.py` | Fala com o LLM via lib `ollama` (chamada direta) | Client |
| `langchain_client.py` | Idem, via LangChain (pode não carregar — ver §6) | Client |
| `tools/search.py` | `search_web()` — DuckDuckGo via `ddgs` | Infra / DAO |
| `tools/scraper.py` | `fetch_page_text()` — download + extração de texto | Infra / DAO |
| `tools/agent_tools.py` | `web_search` / `read_page` **expostas ao modelo** + `SourceTracker` | Infra |
| `resumos/` | Saída (criada em runtime): 1 `.txt` por pesquisa + log de auditoria | — |

---

## 3. Modo 1 — Pipeline determinístico

O fluxo é fixo, escrito em `for`/`if`. O modelo é chamado só para tarefas
pontuais (moderar, resumir, sintetizar) e **nunca decide o próximo passo**.

```mermaid
flowchart TD
    A["query do usuário"] --> B{"idade &lt; 18?"}
    B -->|sim| C["LLM: tema apropriado para menor?"]
    C -->|"NAO"| D["bloqueia + log BLOQUEADO"]
    C -->|"SIM"| E
    B -->|não| E["search_web: pool de resultados<br/>(max_results x 4)"]
    E --> F{"para cada resultado<br/>até 'max_results' páginas lidas"}
    F --> G["fetch_page_text(url)"]
    G -->|"falhou"| F
    G -->|"ok"| H["LLM: resume esta página"]
    H --> F
    F -->|"coletou o suficiente"| I["LLM: sintetiza os resumos<br/>com citações [n]"]
    I --> J["monta referências IEEE em Python"]
    J --> K["monta cabeçalho de auditoria"]
    K --> L["salva resumos/*.txt + log CONCLUIDO"]
```

---

## 4. Modo 2 — Agente autônomo

Existe um **loop**: a cada rodada o modelo recebe as ferramentas e responde
*"chame a ferramenta X"* ou *"aqui está a resposta final"*. Quem decide **se**
busca, **o que** busca, **quantas vezes** e **quando parar** é o modelo.

```mermaid
flowchart TD
    A["query do usuário"] --> B{"idade &lt; 18?"}
    B -->|sim| C["LLM: tema apropriado?"]
    C -->|"NAO"| D["bloqueia + log"]
    C -->|"SIM"| L
    B -->|não| L["messages = [system_prompt, pergunta]"]
    L --> CHAT["ollama.chat(messages, tools=[web_search, read_page])"]
    CHAT --> DEC{"o modelo pediu<br/>uma ferramenta?"}
    DEC -->|sim| EXE["executa a função Python<br/>anexa resultado como role=tool"]
    EXE --> CHAT
    DEC -->|"não — quer responder"| G{"já leu alguma<br/>página com read_page?"}
    G -->|sim| FINAL["aceita a resposta final"]
    G -->|"não — ainda há 'nudge'"| NUDGE["injeta lembrete<br/>e volta ao loop"]
    NUDGE --> CHAT
    G -->|"não — nudges esgotados"| AUTO["_auto_read: o código lê<br/>as 3 primeiras páginas"]
    AUTO --> CHAT
    FINAL --> REF["referências IEEE só das<br/>páginas realmente lidas"]
    REF --> SAVE["salva resumos/*.txt + log"]
```

### O loop, como troca de mensagens

```mermaid
sequenceDiagram
    actor U as Usuário
    participant AG as AutonomousResearcherAgent
    participant M as LLM (qwen2.5:7b)
    participant T as tools/agent_tools.py
    participant W as Web

    U->>AG: pergunta
    AG->>M: messages [system + pergunta] + lista de tools
    M-->>AG: tool_call web_search
    AG->>T: web_search(query)
    T->>W: DuckDuckGo
    W-->>T: resultados
    T-->>AG: lista de links (title, url, trecho)
    AG->>M: role=tool -> resultados
    M-->>AG: tool_call read_page
    AG->>T: read_page(url)
    T->>W: GET url
    W-->>T: HTML
    T-->>AG: texto principal extraído
    AG->>M: role=tool -> texto
    M-->>AG: resposta final (texto, sem tool_call)
    AG->>AG: monta referências IEEE + cabeçalho de auditoria
    AG-->>U: relatório no terminal + resumos/*.txt
```

### Workflow x Agente, lado a lado

```mermaid
flowchart LR
    subgraph WF["Modo 1 — Workflow (o código decide)"]
      direction TB
      W1["busca"] --> W2["lê N páginas"] --> W3["resume cada uma"] --> W4["sintetiza"]
    end
    subgraph AGT["Modo 2 — Agente (o modelo decide)"]
      direction TB
      A2{"próxima ação?"}
      A2 -->|"1"| A3["web_search"]
      A2 -->|"2"| A4["read_page"]
      A2 -->|"3"| A5["responder e parar"]
      A3 --> A2
      A4 --> A2
    end
```

---

## 5. Ferramentas, segurança e saída

- **Ferramentas** (`tools/agent_tools.py`): o *docstring* de cada função vira a
  descrição que o modelo lê, e a assinatura tipada vira o schema dos argumentos.
  A lib `ollama` faz essa conversão sozinha.
- **Filtro de menor de idade**: checagem determinística **antes** do loop, nos
  dois modos. Segurança não é delegada ao modelo.
- **Referências IEEE**: montadas em Python (`agents/audit.py`) a partir das
  páginas que passaram de fato por `read_page`/`fetch_page_text` — o modelo
  costuma "citar" URLs que inventou; essas são ignoradas.
- **Saída**: `resumos/<timestamp>_<tema>.txt` (cabeçalho de auditoria + síntese +
  referências) e uma linha em `resumos/historico_auditoria.log` para **toda**
  tentativa, inclusive as bloqueadas.

---

## 6. Ambiente e limitações conhecidas

- **Smart App Control (Windows)** ativo neste PC bloqueia DLLs nativas não
  assinadas instaladas via pip:
  - `uuid_utils` (dep de `langchain-core`) → o modo 1 com **LangChain** quebra no
    import; `main.py` detecta e volta pro Ollama direto sozinho.
  - `lxml` (dep de `trafilatura`) → por isso `tools/scraper.py` tem um **fallback
    puro-Python** (`html.parser` + `httpx`), com qualidade um pouco menor.
- **Modelo pequeno**: o `qwen2.5:7b` às vezes se recusa a usar as ferramentas e
  tenta responder "de cabeça". O modo 2 tem dois freios determinísticos
  (`GROUNDING_NUDGE` e `_auto_read`) para garantir que a resposta seja
  fundamentada. Com um modelo maior ou via API, esses freios quase não disparam.

---

## 7. Como rodar

Pré-requisito: **app do Ollama aberto** (servidor em `localhost:11434`) com o
modelo baixado — `ollama pull qwen2.5:7b`.

```bat
:: sempre pelo Python do venv (NÃO use "py" ou "python" direto)
.venv\Scripts\python.exe main.py
```

Ou ativando o ambiente primeiro:

```bat
.venv\Scripts\activate
python main.py
```

Instalação das dependências (uma vez):

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No menu, escolha **1** (pipeline determinístico) ou **2** (agente autônomo).
No modo 2, cada ferramenta que o modelo decide chamar aparece em *magenta* no
terminal, em tempo real.

---

## 8. Como visualizar os diagramas

Os blocos ` ```mermaid ` acima renderizam direto no GitHub/GitLab e no preview de
Markdown do VS Code (extensão *Markdown Preview Mermaid Support*). Para exportar
imagem: cole o código em <https://mermaid.live> e baixe PNG/SVG.
