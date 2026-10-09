# Do pipeline para o agente autônomo

Este documento explica a Fase 2 do projeto: a diferença concreta entre o que
existia (`agents/researcher_agent.py`) e o agente autônomo novo
(`agents/autonomous_agent.py`), e como rodar cada um.

## 1. A pergunta original: "isso é um agente?"

O critério prático é **quem decide a sequência de passos**:

| | Quem decide o fluxo | Nome mais preciso |
|---|---|---|
| Script antigo (`input` → `ollama.chat` → `print`) | ninguém, é uma chamada só | chamada de API |
| `researcher_agent.py` | o seu código (`for`/`if` fixos) | *workflow* / pipeline |
| `autonomous_agent.py` | o **modelo**, num loop de tool-calling | agente |

No pipeline, o `run()` sempre faz: buscar → ler N páginas → resumir cada uma →
sintetizar. O modelo nunca escolhe nada — ele só executa tarefas pontuais
(moderar, resumir, sintetizar). É determinístico.

No agente autônomo existe um **loop**: a cada rodada o modelo recebe a lista de
ferramentas e responde uma de duas coisas:

- "chame a ferramenta X com estes argumentos" → o código executa e devolve o
  resultado pro modelo, e o loop continua;
- um texto normal, sem pedir ferramenta → é a resposta final, o loop para.

Quem decide *se* busca, *o que* busca, *quantas vezes*, *quais páginas ler* e
*quando já tem informação suficiente* é o modelo.

## 2. As três peças novas

```
tools/agent_tools.py        # web_search e read_page descritas PARA O MODELO (docstring vira o schema)
agents/audit.py             # auditoria/relatório/referências compartilhados pelos dois agentes
agents/autonomous_agent.py  # o loop de tool-calling
```

`tools/search.py` e `tools/scraper.py` continuam iguais e são reaproveitados por
baixo — a diferença é que em `agent_tools.py` as funções são expostas ao modelo.

### O loop, em pseudocódigo

```
messages = [system_prompt, pergunta_do_usuário]
repita até MAX_STEPS:
    resposta = ollama.chat(model, messages, tools=[web_search, read_page])
    messages.append(resposta)
    se resposta não pediu ferramenta:
        resposta_final = resposta.texto
        pare
    para cada ferramenta pedida:
        resultado = executa a função Python correspondente
        messages.append({role: "tool", content: resultado})
```

É isso que `create_react_agent` / `AgentExecutor` do LangChain fazem internamente.
Aqui está escrito à mão (~50 linhas em `run()`) por dois motivos: é mais fácil de
estudar, e o `langchain-core` **não carrega neste PC** (ver seção 4).

## 3. O que continua sob controle do código (de propósito)

- **Filtro para menores de idade**: é uma checagem determinística *antes* do loop.
  Segurança não é delegada ao agente.
- **Referências IEEE**: montadas em Python a partir das páginas que passaram de
  fato por `read_page` (`SourceTracker`). O modelo costuma "citar" URLs que
  inventou; essas são ignoradas.
- **Dois empurrões**, porque o qwen2.5:7b é pequeno e às vezes ignora as
  ferramentas:
  1. `GROUNDING_NUDGE` — se ele tenta responder sem ler nada, o código manda um
     lembrete e deixa ele tentar de novo (até 2 vezes).
  2. `_auto_read` — se mesmo assim ele não lê, o código abre as 3 primeiras
     páginas dos resultados e devolve o texto pro modelo sintetizar.
  Com um modelo maior (ou via API) esses empurrões raramente disparam.
- **Auditoria e salvamento**: iguais ao pipeline, com linhas extras (rodadas de
  decisão, nº de buscas, nº de páginas lidas) no cabeçalho.

## 4. Ambiente: Smart App Control bloqueia DLLs nativas

Este PC está com o **Smart App Control** do Windows ativo e *enforcing*. Ele
bloqueia `.pyd` (DLLs) nativos não assinados instalados via pip. No projeto isso
afeta:

- `uuid_utils` (dependência do `langchain-core`) → o caminho **LangChain** do
  pipeline (opção 2 do menu) quebra no import. O `main.py` detecta e volta pro
  Ollama direto sozinho.
- `lxml` (dependência do `trafilatura`) → a extração de texto das páginas. Por
  isso `tools/scraper.py` agora tem um **fallback puro-Python** (`html.parser` +
  `httpx`) que roda quando o `trafilatura` não importa. Qualidade um pouco menor,
  mas funciona.

Para usar o `trafilatura`/LangChain de verdade seria preciso desligar o Smart App
Control em *Segurança do Windows → Controle de aplicativos e navegador* (atenção:
uma vez desligado, só volta a ligar reinstalando o Windows).

## 5. Como rodar

```
.venv\Scripts\python.exe main.py
```

O menu novo pergunta primeiro o **modo**:

```
1 - Pipeline determinístico (o código Python decide cada passo)
2 - Agente autônomo (o modelo decide quando buscar, ler e parar)
```

No modo 1, ele ainda pergunta o motor (Ollama direto / LangChain), como antes.
No modo 2, o agente autônomo mostra em *magenta* cada ferramenta que o modelo
decide chamar, pra você acompanhar o raciocínio dele em tempo real.

Pré-requisito dos dois modos: o app do **Ollama** aberto (servidor em
`localhost:11434`) com o modelo `qwen2.5:7b` baixado.
