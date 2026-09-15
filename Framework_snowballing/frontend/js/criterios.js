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
const ANALYSIS_BATCH_SIZE = 40;

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
    abstract: limitarTexto(artigo.abstract, 650),
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

async function analisarEmLotes(artigos, criteriosInclusao, criteriosExclusao, criteriaMetadata = {}) {
  const artigosLimpos = prepararArtigosParaAnalise(artigos);
  const tamanhoLote = ANALYSIS_BATCH_SIZE;
  const lotes = dividirEmLotes(artigosLimpos, tamanhoLote);
  const resultadosFinais = [];

  const statusEl = document.getElementById('statusAnalise');
  const progressoEl = document.getElementById('progressoAnalise');
  const progressContainer = document.querySelector('.progress');

  if (progressContainer) {
    progressContainer.style.display = '';
  }
  statusEl.style.display = '';

  statusEl.textContent = `Starting analysis... 0/${artigosLimpos.length}`;
  progressoEl.style.width = '0%';
  progressoEl.textContent = '0%';

  for (let i = 0; i < lotes.length; i++) {
    const lote = lotes[i];

    const payload = {
      criteriosInclusao: criteriosInclusao,
      criteriosExclusao: criteriosExclusao,
      criteriaMetadata: criteriaMetadata,
      artigos: lote,
      extraPrompt: localStorage.getItem('llmPrompt') || '',
    };

    const res = await fetch('/api/articles/analisar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      let detalhe = '';
      try {
        detalhe = (await res.json()).error || '';
      } catch {
        detalhe = res.statusText;
      }
      throw new Error(`Error analyzing batch ${i + 1}${detalhe ? `: ${detalhe}` : ''}`);
    }

    const resultadosLote = await res.json();
    resultadosFinais.push(...resultadosLote);

    const processados = Math.min((i + 1) * tamanhoLote, artigosLimpos.length);
    const percentual = Math.round((processados / artigosLimpos.length) * 100);

    statusEl.textContent = `Analyzing articles... ${processados}/${artigosLimpos.length}`;
    progressoEl.style.width = `${percentual}%`;
    progressoEl.textContent = `${percentual}%`;
  }

  statusEl.textContent = `Analysis finished: ${artigosLimpos.length}/${artigosLimpos.length}`;
  progressoEl.style.width = '100%';
  progressoEl.textContent = '100%';
  setTimeout(() => {
    if (progressContainer) {
      progressContainer.style.display = 'none';
    }
    statusEl.style.display = 'none';
  }, 800);

  return resultadosFinais;
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

  btnTexto.classList.add('d-none');
  btnLoading.classList.remove('d-none');
  analisarBtn.disabled = true;

  try {
    const resultados = await analisarEmLotes(
      artigosIncluidos,
      inclusao,
      exclusao,
      criteriaMetadata
    );
    const divResultado = document.getElementById('resultadoAnalise');
    divResultado.dataset.resultadosRaw = JSON.stringify(resultados);

    document.getElementById('selectedTitle').style.display = 'none';

    document.getElementById('analysisSection').classList.remove('d-none');
    document.getElementById('analysisSection').classList.add('d-flex');

    mostrarTabelaComResultados(artigosIncluidos, resultados);
    await salvarCriteriosNoBanco(resultados);
  } catch (err) {
    alert('Error: ' + err.message);
    const divResultado = document.getElementById('resultadoAnalise');
    // textContent: a mensagem pode trazer texto vindo do provedor da LLM.
    const erroEl = document.createElement('p');
    erroEl.className = 'text-danger';
    erroEl.textContent = err.message;
    divResultado.replaceChildren(erroEl);
    divResultado.dataset.resultadosRaw = '';
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