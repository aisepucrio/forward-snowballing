// Extrai, das linhas de diagnóstico que os scripts Python imprimem no stderr,
// apenas o que interessa a quem está esperando a busca terminar.
//
// A busca leva ~50s e pode passar de 3 minutos, e a tela mostrava só um
// spinner. O que resolve isso não é detalhar o que o pipeline faz por dentro —
// é adiantar o número que o usuário veria na tela seguinte, para ele saber que
// a busca está de fato voltando com algo.
//
// Por isso, deliberadamente NÃO viram mensagem: estado do cache, nome das
// fontes consultadas, contagens por fonte, fusão/deduplicação, gravação em
// banco e falhas de API. Isso é diagnóstico — vive no stderr, no log do
// servidor e nos testes, não na interface.
//
// Também não são usados os totais parciais (o que cada fonte trouxe antes da
// deduplicação): eles ENCOLHEM quando as duplicatas são removidas, e um número
// que diminui na tela parece defeito. Só a contagem final é publicada.

const CONTAGEM_FINAL = /^\[SOURCE COUNTS\] Final \w+: citations=(\d+), references=(\d+)/;

function parseProgressLine(line) {
  const text = String(line || '').trim();
  if (!text) return null;

  const match = text.match(CONTAGEM_FINAL);
  if (!match) return null;

  const citations = Number(match[1]);
  const references = Number(match[2]);

  return {
    stage: 'counts',
    citations,
    references,
    message: `${citations} citations · ${references} references`,
  };
}

module.exports = {
  parseProgressLine,
};
