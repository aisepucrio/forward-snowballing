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

## Próximo passo sugerido

Usar a lista `reference` do **Crossref** como fonte do backward. Hoje ela é
ignorada: `crossref_item_to_result` só lê metadados. Nos artigos medidos, ela
bateu exatamente com o gabarito em 2 de 2 casos (77 e 28) e cobre justamente o
caso da lista bloqueada na Semantic para editoras como a Elsevier
(10.1016/j.infsof.2016.07.006: Semantic bloqueado, Crossref 77 = real).

## Limitações

- O teste compara totais, não identidade. Um total certo pode esconder itens
  errados. Para medir precisão/recall é preciso gabarito com a lista real de
  referências de cada artigo.
- 5 artigos é uma amostra pequena; a lista completa (16 entradas) roda com
  `INPUT_CSV=tests_csvs/tests_csvs.csv MAX_ENTRADAS=16`.
