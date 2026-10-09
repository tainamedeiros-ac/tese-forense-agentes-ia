# Guia completo do projeto `mult-agent`

Este documento explica o projeto do zero: o que ele faz, como o código Python se compara ao que você já conhece em Java, o que é um "agente" de IA na prática, e principalmente **o que acontece por trás dos panos na sua máquina** quando você roda isso — incluindo por que o `qwen2.5:7b` fica vivo no Gerenciador de Tarefas.

---

## 1. O que o projeto faz, em uma frase

Você digita um tema no terminal → o agente busca no DuckDuckGo → abre cada página encontrada e extrai o texto → manda cada texto para um modelo de linguagem (LLM) rodando **localmente na sua máquina** resumir → junta os resumos em uma síntese final com citações estilo IEEE → salva tudo (com cabeçalho de auditoria) em um `.txt` e registra a consulta num log de histórico.

## 2. Python para quem vem de Java — mapa mental rápido

Você não precisa aprender Python "do zero" — a maior parte dos conceitos tem equivalente direto em Java. Aqui está o dicionário de tradução usando o próprio código do projeto:

| Java | Python (neste projeto) | Onde está |
|---|---|---|
| `class` com campos + getters/setters, ou um `record` | `@dataclass` — gera `__init__`, comparação, `repr` automaticamente a partir dos campos declarados | `PageSummary`, `SearchResult` |
| Interface/contrato de método | Não existe interface formal; Python usa "duck typing" — se o objeto tem o método certo, funciona. Não há compilador checando isso, só o `mypy`/IDE avisando (não bloqueando) | em geral |
| `Optional<String>` | `str \| None` (union type). É só uma **anotação**, não é imposta em runtime como o `Optional` do Java força via API | `search_pool_size: int \| None = None` |
| Maven/Gradle (`pom.xml`/`build.gradle`) | `pip` + `requirements.txt` — lista de dependências, mas sem grafo de versões tão robusto quanto o Maven | `requirements.txt` |
| Repositório central `~/.m2` compartilhado entre projetos | **Não existe por padrão** — cada projeto Python geralmente tem sua própria cópia física dos pacotes dentro da pasta `.venv/Lib/site-packages`. É como se cada projeto tivesse seu próprio "JRE + classpath" isolado | pasta `.venv/` |
| `javac` compila e barra erros antes de rodar | Python é **interpretado linha a linha** — um erro de digitação num método só aparece quando aquela linha específica é executada, não no "build" | por isso o `ModuleNotFoundError` só apareceu quando você rodou, não antes |
| Pacote Java = `package com.empresa.projeto;` + estrutura de pastas correspondente, imposto pelo compilador | Pacote Python = pasta com (opcionalmente) um `__init__.py` dentro. Bem mais solto — só precisa que a pasta exista no caminho de import | pastas `agents/`, `tools/` |
| `String.format("%s tem %d anos", nome, idade)` | f-string: `f"{nome} tem {idade} anos"` | usado em quase todo lugar, ex. `f"Usuário: {self.user_name}"` |
| `List<String> resultado = lista.stream().map(...).collect(...)` | *list comprehension*: `[transformar(x) for x in lista]` | `[p for p in page_summaries if p.summary]` (padrão usado no projeto) |
| Método `private` de uma classe | Convenção: prefixo `_nome_do_metodo` (não é imposto pela linguagem, é uma combinação social) | `_build_audit_header`, `_save_to_file` |
| `try (Connection c = ...) { }` (try-with-resources) | `with arquivo.open(...) as f: ...` — mesmo conceito, fecha o recurso automaticamente ao sair do bloco | `_log_history`, `_save_to_file` |

## 3. O que é um "agente" de IA, de verdade

Esquece o hype por um segundo. Tecnicamente, um agente aqui é **código Python comum orquestrando chamadas** — não tem mágica. A diferença entre "só chamar uma API de IA" e "ter um agente" é:

1. **O LLM sozinho só sabe o que aprendeu no treinamento.** Ele não sabe notícias de hoje, não sabe o que está numa página específica. Por isso o agente busca informação de fora (web) **antes** de perguntar pro modelo — isso chama-se *grounding* (fundamentar a resposta em dados reais, não só na "memória" do modelo).
2. **O agente decide o fluxo, em Python puro, sem IA nenhuma decidindo por ele.** Quantas páginas buscar, o que fazer se uma falhar, quando parar — tudo isso é `if`/`for`/`while` comum, exatamente como você escreveria numa classe de serviço em Java. O "agente" não é autônomo no sentido de "pensa sozinho o que fazer"; é sequencial e determinístico.
3. **O LLM é chamado várias vezes, com papéis diferentes**, e a saída de uma chamada vira entrada da próxima:
   - 1ª chamada (por página): "resuma este texto" (`SUMMARY_SYSTEM_PROMPT`)
   - 2ª chamada (uma vez): "combine estes resumos numa síntese com citações" (`FINAL_SYSTEM_PROMPT`)
   - Chamada condicional extra (se `idade < 18`): "esse tema é apropriado pra um menor?" (`MODERATION_SYSTEM_PROMPT`)

   Isso é literalmente equivalente a **encadear chamadas de método**, só que um dos "métodos" (`ask()`, em `llm_client.py`) não roda lógica determinística — ele manda um texto pra um modelo estatístico e recebe outro texto de volta, sem garantia formal do formato da resposta (diferente de uma chamada REST tipada com JSON schema).

Em resumo: um "agente" = **um orquestrador Python que decide quando chamar ferramentas externas (busca, scraping) e quando chamar um LLM**, e vai montando um resultado final a partir dessas peças. Nada mais místico que isso.

> **Atualização (Fase 2):** o projeto agora tem **dois** agentes. O
> `researcher_agent.py` é o descrito acima (fluxo fixo no código). O
> `autonomous_agent.py` é a versão em que **o modelo dirige o loop**: ele recebe
> as ferramentas e decide sozinho o que chamar e quando parar. Essa é a fronteira
> entre "workflow" e "agente autônomo". Veja `AGENTE_AUTONOMO.md`.

## 4. Estrutura de arquivos e responsabilidades

```
mult-agent/
├── main.py                       # CLI: pergunta modo + nome/idade, depois fica em loop pedindo temas
├── llm_client.py                  # porta de entrada para o LLM local (Ollama, chamada direta)
├── langchain_client.py            # idem, via LangChain (pode não carregar — ver AGENTE_AUTONOMO.md §4)
├── agents/
│   ├── audit.py                      # auditoria/relatório/referências compartilhados
│   ├── researcher_agent.py           # MODO 1: pipeline determinístico (o código decide o fluxo)
│   └── autonomous_agent.py           # MODO 2: agente autônomo (o modelo decide o fluxo via tool-calling)
├── tools/
│   ├── search.py                     # busca no DuckDuckGo (biblioteca ddgs)
│   ├── scraper.py                     # baixa uma URL e extrai o texto (trafilatura, com fallback puro-Python)
│   └── agent_tools.py                 # web_search/read_page expostas AO MODELO no modo 2
└── resumos/                       # criada em runtime — saída dos resumos + log de auditoria
    ├── <timestamp>_<pergunta>.txt      # um arquivo por pesquisa concluída
    └── historico_auditoria.log         # log persistente (append) de TODAS as tentativas
```

Regra de dependência (equivalente a "camadas" numa arquitetura Java em pacotes):
**`tools` não conhece `agents`; `agents` conhece `tools` e `llm_client`; `main` só conhece `agents`.**
Pense em `tools/` como sua camada de "infra" (clients/DAOs), `agents/` como camada de "serviço" (orquestra regra de negócio), `main.py` como sua camada de "controller/CLI".

## 5. O fluxo passo a passo (`ResearcherAgent.run`)

1. **Filtro de menor de idade** (se `user_age < 18`): manda o *tema* pro LLM com `MODERATION_SYSTEM_PROMPT`, pedindo só "SIM" ou "NAO". Se "NAO", bloqueia, registra no log (`_log_history`, status `BLOQUEADO`) e retorna sem pesquisar nada.
2. **Busca** (`search_web`): pede um "pool" de resultados maior que o necessário (`max_results * 4`) ao DuckDuckGo, prevendo que algumas páginas vão falhar ao abrir.
3. **Leitura + resumo por página**: para cada resultado do pool, tenta baixar/extrair o texto (`fetch_page_text`). Se falhar, pula pro próximo do pool (não desiste mais na primeira falha). Se der certo, manda o texto pro LLM resumir (`SUMMARY_SYSTEM_PROMPT`). Para assim que atingir `max_results` resumos bem-sucedidos.
4. **Síntese final**: junta os resumos numerados (`[1]`, `[2]`, `[3]`) num prompt só, e pede ao LLM uma síntese única que cite as fontes inline (`FINAL_SYSTEM_PROMPT`).
5. **Referências IEEE**: montadas em **código Python puro** (`_build_references`), não pelo LLM — isso garante que URL e título fiquem exatos, sem o modelo "inventar" nada.
6. **Cabeçalho de auditoria** (`_build_audit_header`): usuário, idade, a pergunta feita, data/hora, navegador padrão do SO, motor de busca, modelo LLM usado, versão do agente.
7. **Salvamento**: grava tudo (`audit_header` + síntese + referências) em `resumos/<timestamp>_<pergunta>.txt`, e registra a conclusão no log de histórico (`historico_auditoria.log`).

## 6. O que acontece de verdade na sua máquina (Ollama)

Isso é a parte que gera mais confusão, então vamos com calma.

### O que é o Ollama

O Ollama é um **programa servidor** que você instalou separadamente (não é uma lib Python, é um aplicativo). Quando ele está rodando, ele abre um servidor HTTP local na porta `11434` do seu computador (`http://localhost:11434`) — igual a se você rodasse um Postgres ou um Redis localmente antes de rodar uma aplicação Spring Boot que conecta nele.

O `main.py` **não roda a IA dentro dele mesmo**. Ele só é um cliente HTTP: a biblioteca `ollama` (usada em `llm_client.py`, na função `ask()`) manda uma requisição pra esse servidor local e espera a resposta. É conceitualmente igual a um `RestTemplate`/`HttpClient` em Java chamando uma API — só que a "API" está rodando na sua própria máquina, não na nuvem.

### Por que o modelo "fica vivo" depois que o script termina

1. Quando você fecha o `main.py` (Ctrl+C), você só encerra o **script Python** — o cliente HTTP. O **servidor Ollama continua rodando** independentemente, exatamente como um banco de dados continua no ar depois que você fecha sua aplicação que conectava nele.
2. Na primeira vez que você chama `ask()`, o Ollama carrega os pesos do modelo `qwen2.5:7b` (uns 4–5 GB) do disco pra **memória RAM (e VRAM da GPU, se você tiver uma compatível)**. Isso é lento (segundos) porque é um arquivo grande sendo lido e organizado em memória.
3. Pra não repetir esse custo em toda pergunta, o Ollama **mantém o modelo carregado em memória por um tempo** depois do último uso (`keep_alive`, padrão de 5 minutos). Só depois desse tempo ocioso ele descarrega o modelo da RAM — mas o **processo do servidor Ollama em si continua rodando**, só consumindo memória mínima quando ocioso.
4. É por isso que você vê `ollama.exe` / `ollama app.exe` no Gerenciador de Tarefas mesmo sem estar rodando o `main.py` — o servidor foi projetado pra ficar residente em segundo plano (igual a um serviço do Windows), pra você não precisar esperar o carregamento toda vez que for usar.

### Isso é normal, mas você tem controle

- **Matar o processo no Gerenciador de Tarefas não quebra nada.** É seguro, igual parar um serviço de banco local. Da próxima vez que rodar `main.py`, o Ollama (se você reabrir o app) vai só recarregar o modelo do zero na primeira chamada — só vai ser mais lento naquela primeira pergunta.
- **Forma "certa" de encerrar**: clique com o botão direito no ícone do Ollama na bandeja do sistema (perto do relógio) → **Quit/Sair**. Isso encerra o servidor de forma organizada, em vez de matar o processo à força.
- **Quanto de RAM ele usa parado (ocioso, sem modelo carregado)?** Pouco — o processo servidor em si é leve. O consumo pesado (os tais 4–5 GB) só existe enquanto o modelo está carregado, ou seja, durante e logo após o uso.
- **Quer que ele não fique residente?** Não tem uma opção nativa simples pra "matar sozinho depois de usar" sem você mesmo fechar — o Ollama foi desenhado pra ficar como serviço de fundo por design (evitar esse custo de recarregar é o ponto principal dele existir). Se isso incomoda, a alternativa é você mesmo fechar manualmente pela bandeja do sistema depois de terminar de usar o `main.py`.

## 7. Resumo mental de uma execução completa

```
Você roda: .venv\Scripts\python.exe main.py
   └─ main.py pergunta nome/idade (uma vez)
   └─ loop: você digita um tema
        └─ ResearcherAgent.run(tema)
             ├─ (se menor) pergunta ao Ollama: "esse tema é apropriado?"   → HTTP localhost:11434
             ├─ busca no DuckDuckGo (internet, não usa o Ollama)
             ├─ baixa cada página via HTTP direto (sem abrir navegador nenhum)
             ├─ pergunta ao Ollama: "resuma este texto" (por página)      → HTTP localhost:11434
             ├─ pergunta ao Ollama: "sintetize estes resumos com citações" → HTTP localhost:11434
             ├─ monta referências IEEE (Python puro, sem IA)
             ├─ salva resumos/<timestamp>_<tema>.txt
             └─ registra em resumos/historico_auditoria.log
```

O Ollama (servidor + modelo carregado) é o único "vizinho" rodando fora do seu script — tudo o mais (busca, scraping, montagem de referências, log) é Python comum, sem IA nenhuma envolvida.
