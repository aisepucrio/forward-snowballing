# Relatório — acurácia do backward (27/10/2026)

## Escopo

5 artigos problemáticos (`tests_csvs/problematicos.csv`), 2 execuções cada, via
`tests_csvs/test_consistency.py`. Causas investigadas com
`tests_csvs/diagnose_backward.py`, que compara as listas brutas de Semantic
Scholar, OpenAlex e OpenCitations com o resultado final (detalhes em
`tests_csvs/diagnostics/`).

## Resultado

| Artigo (DOI) | Real | Antes | Depois | Crossref | Situação |
|---|---|---|---|---|---|
| 10.1016/j.jss.2021.111044 | 110 | 160 | **141** | 139 | gabarito suspeito |
| 10.5277/e-Inf180103 | 75 | 5 | 5 | não indexado | Semantic bloqueado |
| 10.1016/j.infsof.2016.07.006 | 77 | 75 / **30** | **76** | 77 | ok |
| 10.1016/j.infsof.2020.106294 | 28 | 37 / 33 | **30** | 28 | ok |
| 10.1049/ic.2011.0001 | 23 | 12 | 12 | 0 | Semantic bloqueado |

- Estabilidade: as 10 execuções usaram o Semantic e as duas execuções de cada
  artigo deram o mesmo número (antes, 2 artigos variavam entre execuções).
- Dentro de ±10% do real: 2 de 5 (antes 1 de 5). Contando o artigo 1 contra o
  Crossref, seriam 3 de 5.
- Erro percentual médio: 44% → 36%. O que sobra vem quase todo dos 2 artigos
  com lista bloqueada.

## Causas encontradas e correções

1. **Semantic caía por rate limit → resultado só do OpenAlex.**
   A Semantic devolve 429 já na 2ª requisição pesada, mesmo com chave, e só
   libera após ~5 s; `safe_get` desistia em ~3 s. Era a origem da variação
   75 → 30. *Correção:* até 6 tentativas em 429 (espera máx. ~23 s)
   — `scripts/services/search.py`, `safe_get`.

2. **Mesma referência contada duas vezes (Semantic + OpenAlex).**
   A chave de identidade é o DOI ou, sem DOI, o título. Quando um lado tem DOI
   e o outro não, ou os DOIs diferem (arXiv vs. publicado, edições de livro,
   DOI com erro de digitação), o par não casava: 18 duplicatas no artigo 1 e 4 no
   artigo 4. *Correção:* no merge de referências, o OpenAlex só entra se não
   casar com o Semantic por DOI **nem** por título (igual, similaridade ≥ 0,90
   ou um prefixo do outro; títulos com menos de 20 caracteres só casam se forem idênticos)
   — `merge_records_across_sources(..., match_titles=True)`.

3. **Volumes de anais do OpenAlex contados como referência.**
   O OpenAlex às vezes resolve a referência para o volume ("Proceedings of the
   18th EASE") em vez do artigo; vem com `type = paratext`. 3 casos no
   artigo 4. *Correção:* com lista do Semantic disponível, registros `paratext`
   do OpenAlex são ignorados (sem ela, ficam, pois são a única pista).

4. **Lixo de parsing de PDF no Semantic.**
   Refs sem `paperId`, sem ano e sem DOI eram frases do corpo do texto
   ("We identified six main different application areas…", "A6 Evolution",
   "RQ3 – What is the performance…"): 5 no artigo 1, 1 no artigo 4.
   *Correção:* `is_semantic_reference_noise` descarta esses registros.

5. **Erros no próprio teste.** A entrada 7 de `tests_csvs.csv` era outro artigo
   (ESEM 2009), não o do gabarito (IST 2009), e por isso ficava sem valor
   real. A entrada 4 estava com o título incompleto. Ambas foram corrigidas.

## Desalinhamentos que permanecem (e por quê)

- **10.1016/j.jss.2021.111044 (141 vs 110):** Crossref (depósito da editora)
  lista 139, Semantic 143 e OpenAlex 135. As três fontes concordam em ~140, o
  que sugere que o gabarito de 110 conta só parte da lista (ex.: sem os estudos
  primários da SLR). **Recomendo revisar esse valor manualmente.**
- **10.5277/e-Inf180103 (5 vs 75) e 10.1049/ic.2011.0001 (12 vs 23):** a
  Semantic sabe a contagem mas não libera a lista (bloqueio da editora), o
  OpenAlex tem só 4 e 12 refs, e o Crossref não tem lista (404 e 0). Não há
  fonte aberta com essas listas; recuperá-las exigiria extrair as referências do
  PDF (ex.: GROBID). Obs.: a Semantic reporta 52 para o segundo, contra 23
  reais, então nem a contagem dela é confiável aqui.
- **10.1016/j.infsof.2020.106294 (30 vs 28):** sobra 1 ref de lixo com ano
  ("Author version of the manuscript accepted for publication", 2020) que a
  heurística não pega, e 1 ref só do OpenAlex.

## Atualização: Crossref como base do backward

A lista de referências que a editora deposita no Crossref (`reference`) passou
a ser a **base** do backward quando existe e está completa (≥ 80% da maior
lista entre Semantic e OpenAlex). Semantic e OpenAlex só completam metadados
das entradas do Crossref e não acrescentam itens. Sem lista no Crossref, o
comportamento anterior continua (Semantic + complemento do OpenAlex +
OpenCitations).

| Artigo | Real (PDF) | Sem Crossref | Com Crossref |
|---|---|---|---|
| 10.1016/j.jss.2021.111044 | 132* | 141 | **131** |
| 10.5277/e-Inf180103 | 75 | 5 | 5 (sem lista no Crossref) |
| 10.1016/j.infsof.2016.07.006 | 77 | 76 | **77** |
| 10.1016/j.infsof.2020.106294 | 28 | 30 | **28** |
| 10.1049/ic.2011.0001 | 23 | 12 | 12 (Crossref tem 0) |
| 10.1007/BF00762210 (busca por título) | 83 | 69 | **83** |

\* Contado no PDF. `valores_reais_artigos.csv` ainda traz 110, que está errado.

Os 4 artigos com lista no Crossref ficaram com erro de no máximo 1
referência; antes ficavam entre 1 e 14. As 2 execuções de cada artigo deram
o mesmo resultado.

Ajustes necessários para o formato do Crossref (todos com teste unitário em
`scripts/tests/test_crossref_references.py`):

- **Fragmentos:** a editora às vezes deposita só a lista de autores, terminada
  em vírgula, como entrada própria (6 na JSS). Esses fragmentos são
  descartados.
- **Capítulos de livro:** vêm com o título do livro em `volume-title`. Se esse
  título fosse usado, todos os capítulos do mesmo livro seriam fundidos (4 no
  BF00762210). Agora o título do capítulo fica vazio e o livro vai para
  `venue`.
- **Entradas só com texto livre (`unstructured`):** o título vindo de outra
  fonte é procurado dentro desse texto, e só vale se aparecer em uma única
  citação. Sem correspondência, o texto da citação é exibido como título (18 no
  BF00762210).

### Rodada completa (todos os artigos de `tests_csvs/` + amostra samplec)

Foram 44 buscas (por título e por DOI, 2 execuções cada), em cerca de 35 min.
Todas as execuções repetidas deram o mesmo número, e a busca por título e a
por DOI coincidiram em todos os artigos.

| Artigo | Real | Sistema | Δ | Base | Crossref / Semantic / OpenAlex |
|---|---|---|---|---|---|
| JSS 2021 (config. spaces) | 132 | 131 | −1 | Crossref | 133 / 143 / 135 |
| IST 2016 (industry-academia) | 77 | 77 | 0 | Crossref | 77 / bloq. / 80 |
| IST 2020 (hybrid search) | 28 | 28 | 0 | Crossref | 28 / 30 / 34 |
| UML Diagrams (MDPI 2021) | 7 | 7 | 0 | Crossref | 7 / 7 / 6 |
| Procedia 2015 (load forecasting) | 29 | 29 | 0 | Crossref | 29 / 24 / 27 |
| BF00762210 (1989) | 83 | 83 | 0 | Crossref | 83 / bloq. / 69 |
| KM Diagnostics (ACM 2018) | 57 | 55 | −2 | Crossref | 55 / bloq. / 47 |
| SLRs in SE (IST 2009) | 42* | 42 | 0 | Crossref | 42 / 50 / 47 |
| Internet Addiction (2012) | 128 | 138 | +10 | Sem. + OA | — / 136 / 131 |
| Personality in SE (IET 2011) | 23 | 12 | −11 | OpenAlex | 0 / bloq. / 12 |
| KM in Testing (e-Inf 2018) | 75 | 5 | −70 | OpenAlex | — / bloq. / 4 |
| Child abuse and the Internet (2001) | 118 | 31 | −87 | OpenAlex | sem DOI / bloq. / 31 |
| ICSME 2026 | 63 | não encontrado | — | — | não indexado |

\* Contado no PDF: [1]–[42]. O gabarito antigo dizia 52 e foi corrigido.

- Dos 12 artigos encontrados, 6 estão exatos e 2 erram por 1–2 referências.
  No início do dia, só 1 de 7 ficava dentro de ±10%.
- **SLRs in SE (IST 2009):** parecia o único caso em que o Crossref piorava o
  resultado (42 contra 52), mas o PDF tem exatamente 42 referências. O erro
  estava no gabarito. O Semantic (50) e o OpenAlex (47) é que listam a mais. A
  proteção dos 80% decidiu certo e não precisa de ajuste. A união das 3 fontes
  com remoção de duplicatas, simulada como alternativa, daria 51, ou 9 a mais.
- Dois dos 8 gabaritos originais estavam errados (JSS: 110 → 132; SLR 2009:
  52 → 42). Vale conferir no PDF os que ainda não foram verificados, como o KM
  Diagnostics (gabarito 57, Crossref 55).
- **Internet Addiction:** a editora (OMICS) não deposita referências no
  Crossref. Continua o excesso causado por referências que o Semantic liga ao
  paper errado.

Continuam sem solução os artigos cuja editora não deposita referências
(e-Informatica, IET) e os artigos sem DOI. Nesses casos só a extração do PDF
resolveria.

## Limitações

- O teste compara totais, não identidade. Um total certo pode esconder itens
  errados. Para medir precisão/recall é preciso gabarito com a lista real de
  referências de cada artigo.
- 5 artigos é uma amostra pequena; a lista completa (16 entradas) roda com
  `INPUT_CSV=tests_csvs/tests_csvs.csv MAX_ENTRADAS=16`.
