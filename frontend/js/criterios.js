let artigosIncluidos = [];

// Modelo, chave, temperatura e paralelismo da LLM ficam só no .env do
// servidor; o frontend envia apenas critérios, artigos e prompt extra.
// Artigos por requisição ao servidor (cada artigo é uma chamada à LLM). Com
// modelos de raciocínio cada chamada leva dezenas de segundos, e o servidor
// corta a requisição em 10 minutos.
const ANALYSIS_BATCH_SIZE = 8;

function mostrarTabelaArtigos(artigos) {
  const tbody = document.getElementById('tabelaArtigosBody');
  if (!tbody) return;

  if (typeof TableComponent === 'undefined') {
    console.error('TableComponent não foi encontrado. Verifique se o table.js foi carregado.');
    return;
  }

  TableComponent.render({
    target: tbody,
    data: artigos,
    showActions: false
  });
}

window.addEventListener('load', () => {
  try {
    artigosIncluidos = JSON.parse(window.name || '[]').map(a => ({
      ...a,
      abstractExpanded: false,
      keywordsExpanded: false
    }));
  } catch {
    artigosIncluidos = [];
  }

  // search_id não vem no window.name (não quisemos mudar esse formato, que
  // analysis.html também lê) — index.js grava ele à parte no localStorage
  // antes de navegar pra cá, então lemos de lá.
  window.currentSearchId = localStorage.getItem('currentSearchId') || null;

  // Os artigos chegam com found_via_seeds desde a busca; a tag "Seed N" ajuda
  // a saber de qual seed veio cada um na hora de aplicar os critérios.
  window.mostrarTagsSeed = true;

  mostrarTabelaArtigos(artigosIncluidos);
});

// Grava os critérios de inclusão/exclusão + o veredito da LLM por artigo no
// banco, numa única chamada em lote — não bloqueia nem afeta a tela de
// resultados se falhar (ex.: sem search_id, ou banco fora do ar).
async function salvarCriteriosNoBanco(resultados) {
  if (!window.currentSearchId) {
    console.warn('[DB] Sem search_id disponível — critérios não serão salvos no banco.');
    return;
  }

  const criteria = {
    Inclusion: Object.fromEntries(obterTags('inclusaoBox').map((desc, i) => [`IC${i + 1}`, desc])),
    Exclusion: Object.fromEntries(obterTags('exclusaoBox').map((desc, i) => [`EC${i + 1}`, desc])),
  };

  const results = artigosIncluidos.map((artigo, i) => ({
    doi: artigo.doi,
    title: artigo.title,
    results: resultados[i]?.results || {}
  }));

  try {
    const res = await fetch('/api/articles/criteria', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ search_id: window.currentSearchId, criteria, results })
    });

    if (!res.ok) throw new Error('Failed to save criteria to database');

    const data = await res.json();
    console.log(
      `[DB] Critérios salvos: ${data.criteria_saved} critérios, ${data.logs_saved} vereditos` +
      `, ${data.skipped_papers?.length || 0} artigo(s) sem paper correspondente no banco.`
    );
  } catch (err) {
    console.error('[ERRO DB] Falha ao salvar critérios/resultados:', err);
  }
}

function dividirEmLotes(array, tamanhoLote = 1) {
  const lotes = [];
  for (let i = 0; i < array.length; i += tamanhoLote) {
    lotes.push(array.slice(i, i + tamanhoLote));
  }
  return lotes;
}

function prepararArtigosParaAnalise(artigos) {
  const limitarTexto = (valor, limite) => {
    const texto = String(valor || '');
    return texto.length > limite ? `${texto.slice(0, limite)}...` : texto;
  };

  return artigos.map(artigo => ({
    title: limitarTexto(artigo.title, 300),
    // Mesmo limite de MAX_ABSTRACT_CHARS em scripts/services/prompt.py.
    abstract: limitarTexto(artigo.abstract, 2000),
    language: artigo.language,
    year: artigo.year,
    venue: artigo.venue,
    open_access: artigo.open_access,
    keywords: artigo.keywords,
    pages: artigo.pages,
    numpages: artigo.numpages,
    citationCount: artigo.citationCount ?? artigo.citations_count,
  }));
}

function construirColunasCriterios(resultados) {
  const colunas = Array.from(
    new Set((resultados || []).flatMap(r => Object.keys(r?.results || {})))
  );

  return colunas.map(col => ({
    label: col,
    className: 'text-center',
    render: (artigo, index) => {
      const resultado = resultados?.[index] || { results: {} };
      const raw = resultado.results?.[col];
      return TableComponent.formatCriteriaBadge(raw);
    }
  }));
}

function mostrarTabelaComResultados(artigos, resultados) {
  const tbody = document.getElementById('tabelaArtigosBody');
  if (!tbody) return;

  if (typeof TableComponent === 'undefined') {
    console.error('TableComponent não foi encontrado. Verifique se o table.js foi carregado.');
    return;
  }

  if (!artigos || artigos.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">No articles selected.</td></tr>';
    return;
  }

  const extraColumns = construirColunasCriterios(resultados);

  TableComponent.render({
    target: tbody,
    data: artigos,
    showActions: false,
    extraColumns,
    onToggleExpand: () => mostrarTabelaComResultados(artigos, resultados)
  });
}

function jsonParaCSV(resultados) {
  if (!resultados || resultados.length === 0) return '';

  const criteriosSet = new Set();
  resultados.forEach(r => {
    if (r.results) {
      Object.keys(r.results).forEach(c => criteriosSet.add(c));
    }
  });

  const colunas = Array.from(criteriosSet);
  const header = ['Title', ...colunas];
  const linhas = [header.join(',')];

  resultados.forEach(r => {
    const linha = [r.title || ''];
    colunas.forEach(col => {
      let val = r.results?.[col] || '';
      val = String(val);
      if (val.includes(',') || val.includes('"') || val.includes('\n')) {
        val = `"${val.replace(/"/g, '""')}"`;
      }
      linha.push(val);
    });
    linhas.push(linha.join(','));
  });

  return linhas.join('\n');
}

// Progresso da análise salvo no navegador a cada lote, para que uma falha no
// meio (cota do modelo, timeout, servidor fora) não descarte o que já foi
// classificado e a análise possa ser retomada depois.
const PROGRESSO_STORAGE_KEY = 'llmAnalysisProgress';

// Só retoma um progresso salvo para os mesmos artigos, critérios e prompt extra.
function assinaturaAnalise(artigos, criteriosInclusao, criteriosExclusao, extraPrompt) {
  const texto = JSON.stringify([
    artigos.map(artigo => artigo.title || ''),
    criteriosInclusao,
    criteriosExclusao,
    extraPrompt,
  ]);
  let hash = 5381;
  for (let i = 0; i < texto.length; i++) {
    hash = ((hash << 5) + hash + texto.charCodeAt(i)) | 0;
  }
  return `${artigos.length}:${hash}`;
}

function lerProgressoSalvo() {
  try {
    return JSON.parse(localStorage.getItem(PROGRESSO_STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function salvarProgresso(assinatura, resultados) {
  try {
    localStorage.setItem(PROGRESSO_STORAGE_KEY, JSON.stringify({ assinatura, resultados }));
  } catch (err) {
    console.warn('[LLM] Não foi possível salvar o progresso da análise:', err);
  }
}

function limparProgresso() {
  try {
    localStorage.removeItem(PROGRESSO_STORAGE_KEY);
  } catch {
    // Sem localStorage não há progresso a limpar.
  }
}

function erroComResultadosParciais(mensagem, resultadosParciais) {
  const err = new Error(mensagem);
  err.resultadosParciais = [...resultadosParciais];
  return err;
}

// O servidor devolve os resultados na ordem dos artigos: resultados[i] é o
// veredito de artigos[i], e a retomada continua a partir de
// resultadosIniciais.length. Em falha, o erro carrega os resultados parciais.
async function analisarEmLotes(
  artigos,
  criteriosInclusao,
  criteriosExclusao,
  { extraPrompt = '', resultadosIniciais = [], onLoteConcluido = () => {} } = {}
) {
  const artigosLimpos = prepararArtigosParaAnalise(artigos);
  const total = artigosLimpos.length;
  const resultadosFinais = [...resultadosIniciais];
  const lotes = dividirEmLotes(artigosLimpos.slice(resultadosFinais.length), ANALYSIS_BATCH_SIZE);

  mostrarPainelProgresso('running');
  const atualizarProgresso = texto => atualizarPainelProgresso(texto, resultadosFinais.length, total);

  for (const lote of lotes) {
    const primeiro = resultadosFinais.length + 1;
    const ultimo = resultadosFinais.length + lote.length;
    let resultadosLote;

    // Cada lote leva dezenas de segundos: dizer quais artigos estão na LLM
    // agora é o que mostra que a análise está andando.
    atualizarProgresso(primeiro === ultimo
      ? `Analyzing article ${primeiro} of ${total}...`
      : `Analyzing articles ${primeiro}–${ultimo} of ${total}...`);

    try {
      const res = await fetch('/api/articles/analisar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          criteriosInclusao: criteriosInclusao,
          criteriosExclusao: criteriosExclusao,
          artigos: lote,
          extraPrompt: extraPrompt,
        })
      });

      if (!res.ok) {
        let detalhe = '';
        try {
          detalhe = (await res.json()).error || '';
        } catch {
          detalhe = res.statusText;
        }
        throw new Error(detalhe || `HTTP ${res.status}`);
      }

      resultadosLote = await res.json();
      if (!Array.isArray(resultadosLote) || resultadosLote.length !== lote.length) {
        throw new Error('Unexpected response from the server.');
      }
    } catch (err) {
      throw erroComResultadosParciais(`Error analyzing articles ${primeiro}-${ultimo}: ${err.message}`, resultadosFinais);
    }

    resultadosFinais.push(...resultadosLote);
    onLoteConcluido(resultadosFinais);
  }

  mostrarPainelProgresso('done');
  atualizarProgresso('Analysis finished');
  setTimeout(esconderPainelProgresso, 1500);

  return resultadosFinais;
}

// Painel de progresso da análise: escondido até a primeira análise, com um
// estado por vez (running, done, error) que troca ícone e cor da barra.
function mostrarPainelProgresso(estado) {
  const painel = document.getElementById('analysisProgress');
  painel.classList.remove('d-none', 'is-running', 'is-done', 'is-error');
  painel.classList.add(`is-${estado}`);
}

function esconderPainelProgresso() {
  // Uma análise nova pode ter começado nesse meio-tempo.
  const painel = document.getElementById('analysisProgress');
  if (painel.classList.contains('is-done')) painel.classList.add('d-none');
}

function atualizarPainelProgresso(texto, feitos, total) {
  const percentual = total ? Math.round((feitos / total) * 100) : 0;
  document.getElementById('statusAnalise').textContent = texto;
  document.getElementById('progressoContagem').textContent = `${feitos}/${total} · ${percentual}%`;
  document.getElementById('progressoAnalise').style.width = `${percentual}%`;
  document.getElementById('progressoTrilha').setAttribute('aria-valuenow', percentual);
}

function exibirResultados(resultados) {
  document.getElementById('resultadoAnalise').dataset.resultadosRaw = JSON.stringify(resultados);
  document.getElementById('selectedTitle').style.display = 'none';

  const analysisSection = document.getElementById('analysisSection');
  analysisSection.classList.remove('d-none');
  analysisSection.classList.add('d-flex');

  mostrarTabelaComResultados(artigosIncluidos, resultados);
}

function mostrarErroAnalise(mensagem) {
  mostrarPainelProgresso('error');
  // textContent: a mensagem pode trazer texto vindo do provedor da LLM.
  document.getElementById('statusAnalise').textContent = mensagem;
}

document.getElementById('criteriosForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  // Texto digitado e não adicionado entra como critério antes de analisar.
  adicionarCriterio('inclusao');
  adicionarCriterio('exclusao');

  const inclusao = obterTags('inclusaoBox')
    .map((c, i) => `${i + 1}. ${c}`)
    .join('\n');

  const exclusao = obterTags('exclusaoBox')
    .map((c, i) => `${i + 1}. ${c}`)
    .join('\n');

  const btnTexto = document.getElementById('btnTexto');
  const btnLoading = document.getElementById('btnLoading');
  const analisarBtn = document.getElementById('analisarBtn');

  if (!inclusao && !exclusao) {
    alert('Please fill in at least one of the fields with criteria.');
    return;
  }

  if (artigosIncluidos.length === 0) {
    alert('No included articles to analyze.');
    return;
  }

  const extraPrompt = localStorage.getItem('llmPrompt') || '';
  const total = artigosIncluidos.length;
  const assinatura = assinaturaAnalise(artigosIncluidos, inclusao, exclusao, extraPrompt);
  const progresso = lerProgressoSalvo();
  let resultadosIniciais = [];

  if (
    progresso?.assinatura === assinatura &&
    Array.isArray(progresso.resultados) &&
    progresso.resultados.length > 0 &&
    progresso.resultados.length < total
  ) {
    const retomar = confirm(
      `A previous analysis of these articles and criteria stopped at ${progresso.resultados.length}/${total}.\n\n` +
      'OK: resume from where it stopped\nCancel: start over'
    );
    if (retomar) {
      resultadosIniciais = progresso.resultados;
    } else {
      limparProgresso();
    }
  }

  btnTexto.classList.add('d-none');
  btnLoading.classList.remove('d-none');
  analisarBtn.disabled = true;

  try {
    const resultados = await analisarEmLotes(
      artigosIncluidos,
      inclusao,
      exclusao,
      {
        extraPrompt,
        resultadosIniciais,
        onLoteConcluido: parciais => salvarProgresso(assinatura, parciais),
      }
    );
    limparProgresso();
    exibirResultados(resultados);
    // Só grava no banco a análise completa.
    await salvarCriteriosNoBanco(resultados);
  } catch (err) {
    const parciais = err.resultadosParciais || [];
    let mensagem = err.message;

    if (parciais.length > 0) {
      exibirResultados(parciais);
      mensagem =
        `Analysis stopped at ${parciais.length}/${total}. ${err.message}\n` +
        'The results so far are shown below and kept in this browser. ' +
        'Click "Apply Criteria" again with the same criteria to resume.';
    } else {
      document.getElementById('resultadoAnalise').dataset.resultadosRaw = '';
    }

    mostrarErroAnalise(mensagem);
    alert('Error: ' + mensagem);
  } finally {
    btnTexto.classList.remove('d-none');
    btnLoading.classList.add('d-none');
    analisarBtn.disabled = false;
  }
});

document.getElementById('downloadBtn').addEventListener('click', () => {
  const divResultado = document.getElementById('resultadoAnalise');
  const resultadosText = divResultado.dataset.resultadosRaw;

  if (!resultadosText) {
    alert('No results available for download.');
    return;
  }

  let resultados;
  try {
    resultados = JSON.parse(resultadosText);
  } catch {
    alert('Error processing results for download.');
    return;
  }

  const csv = jsonParaCSV(resultados);

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = 'analysis_results.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  URL.revokeObjectURL(url);
});

// ---------------------------------------------------------------------------
// Critérios de inclusão/exclusão
//
// Cada coluna é uma lista (IC1, IC2... / EC1, EC2...) com um campo de
// adicionar sempre visível embaixo.
// ---------------------------------------------------------------------------
const CRITERIOS = {
  inclusao: { prefixo: 'IC', lista: 'inclusaoBox', input: 'inclusaoInput', contador: 'inclusaoCount' },
  exclusao: { prefixo: 'EC', lista: 'exclusaoBox', input: 'exclusaoInput', contador: 'exclusaoCount' },
};

function configDaLista(containerId) {
  return Object.values(CRITERIOS).find(c => c.lista === containerId);
}

function itensCriterio(containerId) {
  return Array.from(document.getElementById(containerId).querySelectorAll(':scope > .criterion-item'));
}

// "IC1: texto" — o prefixo vai junto no prompt, como sempre foi, para a LLM
// devolver os vereditos pelas mesmas chaves.
function obterTags(containerId) {
  const { prefixo } = configDaLista(containerId);
  return itensCriterio(containerId).map((item, i) =>
    `${prefixo}${i + 1}: ${item.querySelector('.criterion-text').textContent.trim()}`
  );
}

function renumerarCriterios(tipo) {
  const config = CRITERIOS[tipo];
  const itens = itensCriterio(config.lista);
  itens.forEach((item, i) => {
    item.querySelector('.criterion-id').textContent = `${config.prefixo}${i + 1}`;
  });
  document.getElementById(config.contador).textContent = itens.length;
}

function editarCriterio(item) {
  if (item.classList.contains('editing')) return;

  const textoEl = item.querySelector('.criterion-text');
  const original = textoEl.textContent;
  const editor = document.createElement('textarea');
  editor.className = 'criterion-editor';
  editor.value = original;
  editor.rows = Math.min(6, Math.max(2, Math.ceil(original.length / 60)));
  editor.setAttribute('aria-label', 'Edit criterion');

  let encerrado = false;
  const encerrar = salvar => {
    if (encerrado) return;
    encerrado = true;
    const novo = editor.value.trim();
    textoEl.textContent = salvar && novo ? novo : original;
    editor.replaceWith(textoEl);
    item.classList.remove('editing');
  };

  editor.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      encerrar(true);
    } else if (e.key === 'Escape') {
      encerrar(false);
    }
  });
  editor.addEventListener('blur', () => encerrar(true));

  item.classList.add('editing');
  textoEl.replaceWith(editor);
  editor.focus();
  editor.setSelectionRange(editor.value.length, editor.value.length);
}

function criarItemCriterio(tipo, texto) {
  const item = document.createElement('li');
  item.className = 'criterion-item';

  item.innerHTML = `
    <span class="criterion-id"></span>
    <p class="criterion-text"></p>
    <div class="criterion-actions">
      <button type="button" class="criterion-action criterion-edit" aria-label="Edit criterion" title="Edit">
        <i class="bi bi-pencil"></i>
      </button>
      <button type="button" class="criterion-action criterion-remove" aria-label="Remove criterion" title="Remove">
        <i class="bi bi-x-lg"></i>
      </button>
    </div>
  `;
  // textContent: o critério é texto livre do usuário.
  item.querySelector('.criterion-text').textContent = texto;

  item.querySelector('.criterion-edit').addEventListener('click', () => editarCriterio(item));
  item.querySelector('.criterion-text').addEventListener('dblclick', () => editarCriterio(item));
  item.querySelector('.criterion-remove').addEventListener('click', () => {
    item.remove();
    renumerarCriterios(tipo);
  });

  return item;
}

// O campo de adicionar começa com uma linha e cresce com o texto (até o
// max-height do CSS, depois rola).
function autoAjustarAltura(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${textarea.scrollHeight + 2}px`;
}

// Adiciona o texto do campo da coluna como critério; devolve false se vazio.
function adicionarCriterio(tipo) {
  const config = CRITERIOS[tipo];
  const input = document.getElementById(config.input);
  const texto = input.value.trim();
  if (!texto) return false;

  document.getElementById(config.lista).appendChild(criarItemCriterio(tipo, texto));
  renumerarCriterios(tipo);
  input.value = '';
  autoAjustarAltura(input);
  return true;
}

document.addEventListener('DOMContentLoaded', () => {
  Object.entries(CRITERIOS).forEach(([tipo, config]) => {
    const input = document.getElementById(config.input);
    input.addEventListener('input', () => autoAjustarAltura(input));
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        adicionarCriterio(tipo);
      }
    });
  });

  document.querySelectorAll('.criteria-add-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tipo = btn.dataset.criteria;
      adicionarCriterio(tipo);
      document.getElementById(CRITERIOS[tipo].input).focus();
    });
  });

  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipTriggerList.forEach(el => {
    new bootstrap.Tooltip(el);
  });
});
