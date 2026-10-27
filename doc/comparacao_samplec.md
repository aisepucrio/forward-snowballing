# Comparação — referências reais (PDF) × sistema · amostra `samplec/` (27/10/2026)

## Como foi feito

- **Real:** as referências foram contadas na seção de referências de cada PDF
  de `samplec/`. Nas listas numeradas, conferi se a sequência estava completa;
  nas de autor-ano, contei pelo padrão "autores, ANO." e conferi a contagem
  manualmente. Os valores estão em `tests_csvs/samplec_valores_reais.csv`.
- **Sistema:** busca **pelo título** (como um usuário faria), 2 execuções por
  artigo, via `tests_csvs/test_consistency.py`:

  ```
  INPUT_CSV=tests_csvs/samplec_titulos.csv \
  VALORES_REAIS_CSV=tests_csvs/samplec_valores_reais.csv \
  OUTPUT_CSV=tests_csvs/samplec_resultados.csv \
  python -X utf8 tests_csvs/test_consistency.py
  ```

## Resultado

| Artigo | Real (PDF) | Sistema | Δ | Fontes (Semantic / OpenAlex) |
|---|---|---|---|---|
| Learning software configuration spaces (JSS 2021) | 132 | 141 | +9 (+6,8%) | 143 / 135 |
| A Review of Short Term Load Forecasting… (Procedia 2015) | 29 | 26 | −3 (−10,3%) | 24 / 27 |
| Child abuse and the Internet (2001, sem DOI) | 118 | 31 | −87 (−74%) | bloqueado (diz 91) / 31 |
| Empowering LLMs with Static Analysis… (ICSME 2026) | 63 | não encontrado | — | não indexado |
| Internet Addiction: A Review (2012) | 128 | 138 | +10 (+7,8%) | 136 / 131 |

As duas execuções de cada artigo deram o mesmo número. Dos 4 artigos que o
sistema encontrou, 2 ficaram dentro de ±10% e 1 ficou no limite (−10,3%).

## Por que cada um diverge

- **JSS (+9).** O Semantic lista 143 itens contra 132 no PDF. Destes, 7 são
  obras que **não estão na lista publicada** (ex.: "A Survey on Compiler
  Autotuning using Machine Learning", "Is It Worth Responding to Reviews?…
  Google Play", "Towards Adversarial Configurations…"). Provavelmente vêm da
  versão preprint (arXiv) do artigo, que o Semantic e o OpenAlex indexam junto
  com a versão publicada. Há ainda 2 lixos de parsing que o filtro atual não
  pega, por terem ano ou paperId ("Silvio Romero de Lemos Meira, and Renata…",
  "DOI: 10.1017/S000… Printed in the United Kingdom"). O OpenAlex acrescenta
  mais 3.
- **Procedia (−3).** Nenhuma fonte tem a lista completa: o Semantic tem 24 e o
  OpenAlex tem 27. Somadas sem duplicatas, dão 26.
- **Child abuse (−87).** O artigo é literatura cinzenta, sem DOI. O sistema
  achou o artigo certo (Stanley, 2001). O Semantic sabe que ele tem 91
  referências, mas não libera a lista; o OpenAlex tem só 31; e sem DOI não há
  como consultar Crossref nem OpenCitations. É limite de cobertura das fontes.
- **ICSME 2026 (não encontrado).** O artigo não está em Semantic, OpenAlex nem
  Crossref. É recente demais ou ainda não foi publicado.
- **Internet Addiction (+10).** O Semantic liga cerca de 6 referências do PDF ao
  paper errado, de outra área (ex.: "Beyond SES: A Resource Model of Political
  Participation", "When News Norms Collide…", "Reduction of cognitive
  dissonance…"). Nenhuma delas está na lista do artigo. O OpenAlex acrescenta
  mais algumas.

### Artigo extra: BF00762210

Steponkus & Lynch (1989), "Freeze/Thaw-Induced Destabilization of the Plasma
Membrane and the Effects of Cold Acclimation", *J. Bioenerg. Biomembr.* 21(1),
DOI 10.1007/BF00762210. É um PDF escaneado; a lista de referências está no
formato autor-ano.

| Real (PDF) | Sistema | Δ | Semantic | OpenAlex | OpenCitations | Crossref |
|---|---|---|---|---|---|---|
| 83 | 69 | −14 (−17%) | bloqueado (diz 61) | 69 | 61 (todas já no OpenAlex) | **83** |

O sistema encontrou o artigo pelo título, e as 2 execuções deram o mesmo
número. As 69 referências vêm todas do OpenAlex. As 14 que faltam são as que
não têm DOI e o OpenAlex não indexa:

- capítulos de livro (5 do *Membranes, Metabolism and Dry Organisms*, entre outros);
- resumos de congresso (*Plant Physiol.* 86, S-53);
- artigos "in press";
- revistas antigas sem DOI (*Cryo-Letters*, *Can. J. Res.*).

O Crossref tem a lista completa (83), mas as entradas sem DOI vêm só como
texto da citação, sem título estruturado.

## Achados para o sistema

1. **Busca por título sem DOI descarta o Semantic.** Em `search_combined`,
   quando o Semantic acha o artigo mas ele não tem DOI, o fluxo segue para o
   OpenAlex e retorna só ele (`attach_openalex_citations`). As referências e
   citações do Semantic se perdem. No "Child abuse" isso não mudou o resultado,
   porque a lista dele estava bloqueada, mas mudaria em outro artigo sem DOI.
2. **O rate limit do Semantic ainda aparece com chamadas seguidas.** No
   diagnóstico, que chama o Semantic duas vezes em sequência, o pipeline caiu
   para "só OpenAlex" uma vez (Internet Addiction: 130). No teste, com uma
   chamada por busca, não caiu.
3. **O gabarito antigo da JSS está errado.** `valores_reais_artigos.csv` diz
   110, mas o PDF tem 132. Recomendo corrigir.
4. **O Semantic e o OpenAlex erram para mais.** Eles incluem referências do
   preprint e ligam referências a papers errados. A contagem do sistema pode
   bater e mesmo assim conter itens que não estão no artigo. Só uma comparação
   item a item mostraria isso.

## Arquivos

- `tests_csvs/samplec_titulos.csv`: entrada (títulos).
- `tests_csvs/samplec_valores_reais.csv`: valores reais, com observações.
- `tests_csvs/samplec_resultados.csv`: saída do teste.
- `tests_csvs/test_consistency.py`: aceita `OUTPUT_CSV` e `VALORES_REAIS_CSV`
  por variável de ambiente.
