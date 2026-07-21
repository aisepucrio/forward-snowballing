# POC — Analytics com linguagem natural e LLM

Esta prova de conceito adapta o princípio do Chat2VIS ao contexto do SnowMap:

```text
pergunta em linguagem natural
  -> LLM gera SQL
  -> validação e consulta SQLite somente leitura
  -> LLM escolhe uma especificação de gráfico em JSON
  -> renderizador local gera e exporta a figura
```

O notebook é autocontido e cria um banco SQLite temporário com artigos, autores e
relacionamentos mockados. Nenhuma mudança é feita na aplicação SnowMap.

## Execução

Abra `snowmap_analytics_poc.ipynb` no Jupyter ou Google Colab e execute as células
na ordem. Na célula de configuração, escolha um provedor:

- `ollama`: usa por padrão `http://localhost:11434/api/chat`;
- `openai`: lê a chave da variável de ambiente `OPENAI_API_KEY`.

No Jupyter local, instale antes as dependências com
`pip install -r poc_analytics_llm/requirements.txt`. O Google Colab normalmente
já inclui essas bibliotecas.

Exemplo de pergunta:

> Mostre a média de autores por artigo em cada ano.

## Decisões de segurança

- A LLM não recebe credenciais nem linhas completas do banco, apenas o esquema.
- Somente uma instrução `SELECT` ou `WITH ... SELECT` é aceita.
- Operações de escrita e comandos administrativos são rejeitados.
- O SQLite usa um autorizador que permite apenas leitura.
- O resultado é limitado a 500 linhas.
- A LLM retorna uma especificação JSON; código Python gerado não é executado.

Essa última decisão difere do protótipo Chat2VIS original, que executa o script
Python produzido pelo modelo com `exec()`. Para integração futura, o esquema
mockado deve ser substituído pelo esquema real criado pela equipe do banco.

## Interface web local

Para testar a POC como uma aplicação, com o Ollama ativo, execute:

```bash
python3 poc_analytics_llm/web_app.py
```

Depois acesse `http://127.0.0.1:8890`. A interface web usa apenas a biblioteca
padrão do Python e não depende de Jupyter, pandas ou matplotlib.
