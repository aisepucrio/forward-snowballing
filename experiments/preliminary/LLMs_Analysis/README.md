# LLMs Analysis

Avaliação da triagem por LLM do SnowMap contra o gabarito humano dos estudos.

As ferramentas daqui rodam **pelo mesmo caminho da aplicação**: o prompt de
`scripts/services/prompt.py` e o cliente de
`scripts/analisys_LLM.py` (OpenRouter, com fallback para a API do
Gemini, novas tentativas e leitura da resposta). Ou seja, o que se mede aqui é o que roda em
produção. Mudou o prompt ou o modelo? Rode de novo e compare.

## Estrutura

```
LLMs_Analysis/
├── code/
│   ├── run_screening.py   # roda a triagem de um estudo e grava os resultados
│   └── compare.py         # compara uma execução com o gabarito e gera as métricas
├── studies/
│   ├── study0/
│   │   ├── start_data/    # articles.json, criteria.json, ground_truth.json
│   │   ├── runs/          # uma pasta por execução: results.json e comparison.txt
│   │   └── history/       # relatórios das rodadas antigas (Gemini e Gemma)
│   └── study1/            # mesma estrutura
└── history/
    └── prompts_legacy.txt # prompts usados nos experimentos antigos
```

| Estudo | Artigos | Critérios | Gabarito |
|---|---|---|---|
| study0 | 109 | 3 inclusão + 4 exclusão | decisão final **e** veredito por critério |
| study1 | 404 | 3 inclusão + 4 exclusão | decisão final (`selected` 0/1) |

## Configuração

As chaves e os parâmetros da LLM vêm do `.env` na raiz do repositório — o mesmo que a
aplicação usa. Veja a tabela de variáveis no README de lá. Em resumo: `OPENROUTER_API_KEY` e
`LLM_MODEL` para o modelo principal, `GEMINI_API_KEY` para o fallback, e
`LLM_MAX_WORKERS` para o paralelismo.

As dependências são as mesmas da aplicação (`requirements.txt` na raiz).

## Uso

Rodar a triagem de um estudo:

```bash
python code/run_screening.py study0
```

Comparar a execução mais recente com o gabarito:

```bash
python code/compare.py study0
```

Opções úteis do `run_screening.py`:

| Opção | Para quê |
|---|---|
| `--limit N` | Analisa só os N primeiros artigos, bom para um teste rápido |
| `--run NOME` | Nomeia a execução (padrão: modelo + data), útil para comparar variações de prompt |
| `--workers N` | Chamadas em paralelo (padrão: `LLM_MAX_WORKERS`) |
| `--fresh` | Ignora o que já foi gravado nessa execução e recomeça |

Os resultados são gravados a cada artigo. Se a execução parar no meio (cota, crédito,
rede), basta rodar de novo com o mesmo `--run` que ela continua de onde parou.

O `compare.py` aceita `--run NOME` para comparar uma execução específica e `--gold CAMINHO`
para usar outro gabarito. O relatório fica em `runs/<execução>/comparison.txt`.

## O que o relatório traz

- **Decisão final:** precision, recall, F1, accuracy e a matriz de confusão, tomando o
  gabarito humano como referência. Um artigo é incluído quando todos os critérios de
  inclusão são "Yes" e nenhum de exclusão é "Yes".
- **Concordância por critério:** quando o gabarito tem veredito critério a critério, como no
  study0. Ajuda a ver *qual* critério a LLM erra, não só quantos artigos.
- **Listas de falsos positivos e negativos**, para inspeção manual.
- **Artigos com erro**, ou seja, aqueles em que a LLM não devolveu resposta válida.

Em revisão sistemática, recall costuma pesar mais que precision: perder um artigo relevante
custa mais caro do que revisar um a mais na leitura completa.
