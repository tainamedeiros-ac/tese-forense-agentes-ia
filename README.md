# tese-forense-agentes-ia

tese-forense-agentes-ia/
├── README.md                      # visão geral, índice e estado atual
│
├── 01-proposta/
│   ├── proposta-tese-en.docx
│   └── sistematizacao-reuniao.docx
│
├── 02-revisao-literatura/
│   ├── controle-artigos.xlsx      # abas Artigos, Resumo, PRISMA
│   ├── fluxo-prisma.drawio
│   ├── mapa-areas-venn.drawio
│   ├── referencias-ieee.md        # lista única, numerada
│   └── pdfs/                      # só uso interno; ver nota abaixo
│
├── 03-arquitetura/
│   ├── arquitetura-scanner.drawio
│   ├── sequencia-scan-forense.drawio
│   └── scanner-ia-forense.docx
│
├── 04-sandbox/
│   ├── especificacao-sandbox.md   # export do doc dos cenários
│   ├── cenarios/                  # um arquivo por cenário (C0, C1, S1...)
│   ├── agente-teste/              # agente Python mínimo
│   ├── coletor-ground-truth/
│   └── runs/                      # saídas das execuções (no .gitignore)
│
├── 05-provas-de-conceito/
│   ├── poc1-deteccao-gguf/        # teste-scan.py + README
│   ├── poc2-cabecalho-gguf/       # comandos PowerShell + print
│   └── poc3-system-prompt/
│
├── 06-ferramenta-scan/            # protótipo final (disco, memória, correlação)
│   ├── src/
│   ├── tests/
│   └── README.md
│
├── 07-resultados/                 # tabelas, gráficos, métricas por cenário
│
└── 00-gestao/
    ├── todo.md                    # pendências com data
    └── atas-reunioes/
