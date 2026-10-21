let artigosIncluidos = [];

const METADATA_FIELDS = [
  { key: 'language', label: 'Language' },
  { key: 'year', label: 'Year' },
  { key: 'venue', label: 'Venue' },
  { key: 'open_access', label: 'Open Access' },
  { key: 'keywords', label: 'Keywords' },
  { key: 'pages', label: 'Pages' },
  { key: 'numpages', label: 'Number of Pages' },
  { key: 'citationCount', label: 'Citation Count' },
];

let metadataUidCounter = 0;

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
  criteriaMetadata = {},
  { extraPrompt = '', resultadosIniciais = [], onLoteConcluido = () => {} } = {}
) {
  const artigosLimpos = prepararArtigosParaAnalise(artigos);
  const total = artigosLimpos.length;
  const resultadosFinais = [...resultadosIniciais];
  const lotes = dividirEmLotes(artigosLimpos.slice(resultadosFinais.length), ANALYSIS_BATCH_SIZE);

  const statusEl = document.getElementById('statusAnalise');
  const progressoEl = document.getElementById('progressoAnalise');
  const progressContainer = document.querySelector('.progress');

  const atualizarProgresso = (texto) => {
    const percentual = Math.round((resultadosFinais.length / total) * 100);
    statusEl.textContent = texto;
    progressoEl.style.width = `${percentual}%`;
    progressoEl.textContent = `${percentual}%`;
  };

  if (progressContainer) {
    progressContainer.style.display = '';
  }
  statusEl.style.display = '';
  statusEl.classList.remove('text-danger');
  statusEl.classList.add('text-muted');
  atualizarProgresso(resultadosFinais.length > 0
    ? `Resuming analysis... ${resultadosFinais.length}/${total}`
    : `Starting analysis... 0/${total}`);

  for (const lote of lotes) {
    const primeiro = resultadosFinais.length + 1;
    const ultimo = resultadosFinais.length + lote.length;
    let resultadosLote;

    try {
      const res = await fetch('/api/articles/analisar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          criteriosInclusao: criteriosInclusao,
          criteriosExclusao: criteriosExclusao,
          criteriaMetadata: criteriaMetadata,
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
    atualizarProgresso(`Analyzing articles... ${resultadosFinais.length}/${total}`);
  }

  atualizarProgresso(`Analysis finished: ${total}/${total}`);
  setTimeout(() => {
    if (progressContainer) {
      progressContainer.style.display = 'none';
    }
    statusEl.style.display = 'none';
  }, 800);

  return resultadosFinais;
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
  const statusEl = document.getElementById('statusAnalise');
  statusEl.style.display = '';
  statusEl.style.whiteSpace = 'pre-line';
  statusEl.classList.remove('text-muted');
  statusEl.classList.add('text-danger');
  // textContent: a mensagem pode trazer texto vindo do provedor da LLM.
  statusEl.textContent = mensagem;
}

document.getElementById('criteriosForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const inclusaoInput = document.getElementById('inclusaoInput');
  const exclusaoInput = document.getElementById('exclusaoInput');

  if (inclusaoInput.value.trim()) {
    criarTag(document.getElementById('inclusaoBox'), inclusaoInput.value.trim(), 'bg-success');
    inclusaoInput.value = '';
  }

  if (exclusaoInput.value.trim()) {
    criarTag(document.getElementById('exclusaoBox'), exclusaoInput.value.trim(), 'bg-danger');
    exclusaoInput.value = '';
  }

  const inclusao = obterTags('inclusaoBox')
    .map((c, i) => `${i + 1}. ${c}`)
    .join('\n');

  const exclusao = obterTags('exclusaoBox')
    .map((c, i) => `${i + 1}. ${c}`)
    .join('\n');

  const criteriaMetadata = {
    ...obterCriteriaMetadata('inclusaoBox'),
    ...obterCriteriaMetadata('exclusaoBox'),
  };

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
      criteriaMetadata,
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

function obterTags(containerId) {
  const container = document.getElementById(containerId);
  const tags = container.querySelectorAll('.badge');

  return Array.from(tags).map(tag => {
    const textEl = tag.querySelector('.criterion-text');
    return (textEl ? textEl.textContent : tag.textContent).trim();
  });
}

function obterCriteriaMetadata(containerId) {
  const container = document.getElementById(containerId);
  const tags = container.querySelectorAll('.badge');
  const prefix = containerId === 'inclusaoBox' ? 'IC' : 'EC';

  const result = {};
  Array.from(tags).forEach((tag, i) => {
    const criterionId = `${prefix}${i + 1}`;
    let fields = [];
    try {
      fields = JSON.parse(tag.dataset.metadataFields || '[]');
    } catch {
      fields = [];
    }
    result[criterionId] = fields;
  });
  return result;
}

function criarTag(container, texto, cor) {
  const input = container.querySelector(':scope > input');

  const tagsAtuais = container.querySelectorAll('.badge');
  const indice = tagsAtuais.length + 1;

  const prefixo = container.id === 'inclusaoBox' ? `IC${indice}` : `EC${indice}`;
  const tagUid = ++metadataUidCounter;

  const tag = document.createElement('span');
  tag.className = `badge d-flex align-items-center ${container.id === 'inclusaoBox' ? 'ic-tag' : 'ec-tag'}`;

  tag.innerHTML = `
    <span class="criterion-text">${prefixo}: ${TableComponent.escapeHtml(texto)}</span>
    <div class="dropdown d-inline-flex metadata-dropdown-wrapper">
      <button type="button" class="metadata-toggle-btn" data-bs-toggle="dropdown"
        data-bs-auto-close="outside" aria-expanded="false"
        title="Choose metadata fields sent to the LLM for this criterion">
        <i class="bi bi-sliders"></i>
      </button>
      <ul class="dropdown-menu dropdown-menu-end p-2 metadata-menu">
        ${METADATA_FIELDS.map(f => `
          <li class="form-check">
            <input class="form-check-input metadata-checkbox" type="checkbox"
              value="${f.key}" id="meta-${tagUid}-${f.key}" checked>
            <label class="form-check-label" for="meta-${tagUid}-${f.key}">${f.label}</label>
          </li>
        `).join('')}
      </ul>
    </div>
    <button type="button" class="btn-close btn-close-white ms-2 remove-tag-btn" style="font-size:0.6rem;"></button>
  `;

  const checkboxes = tag.querySelectorAll('.metadata-checkbox');
  const syncMetadataDataset = () => {
    const selected = Array.from(checkboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value);
    tag.dataset.metadataFields = JSON.stringify(selected);
  };
  checkboxes.forEach(cb => cb.addEventListener('change', syncMetadataDataset));
  syncMetadataDataset();

  tag.querySelector('.remove-tag-btn').addEventListener('click', () => {
    tag.remove();

    const restantes = container.querySelectorAll('.badge');
    restantes.forEach((t, i) => {
      const newPrefix = container.id === 'inclusaoBox' ? `IC${i + 1}` : `EC${i + 1}`;
      const textEl = t.querySelector('.criterion-text');
      const criterionBody = textEl.textContent.slice(textEl.textContent.indexOf(':') + 1).trim();
      textEl.textContent = `${newPrefix}: ${criterionBody}`;
    });

    if (restantes.length === 0) {
      input.placeholder = container.id === 'inclusaoBox'
        ? 'Enter inclusion criteria...'
        : 'Enter exclusion criteria...';
    }
  });

  container.insertBefore(tag, input);
  input.placeholder = '';
}

function ativarInputTags(inputId, boxId, cor) {
  const input = document.getElementById(inputId);
  const box = document.getElementById(boxId);

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();

      const texto = input.value.trim();
      if (!texto) return;

      criarTag(box, texto, cor);
      input.value = '';
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  ativarInputTags('inclusaoInput', 'inclusaoBox', 'bg-success');
  ativarInputTags('exclusaoInput', 'exclusaoBox', 'bg-danger');

  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipTriggerList.forEach(el => {
    new bootstrap.Tooltip(el);
  });
});