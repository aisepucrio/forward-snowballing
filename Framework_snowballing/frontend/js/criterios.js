let artigosIncluidos = [];

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

  mostrarTabelaArtigos(artigosIncluidos);
});

function dividirEmLotes(array, tamanhoLote = 1) {
  const lotes = [];
  for (let i = 0; i < array.length; i += tamanhoLote) {
    lotes.push(array.slice(i, i + tamanhoLote));
  }
  return lotes;
}

function prepararArtigosParaAnalise(artigos) {
  return artigos.map(artigo => ({
    title: artigo.title || '',
    abstract: artigo.abstract || ''
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

async function analisarEmLotes(artigos, criteriosInclusao, criteriosExclusao) {
  const artigosLimpos = prepararArtigosParaAnalise(artigos);
  const tamanhoLote = 10;
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
      artigos: lote
    };

    const res = await fetch('/api/articles/analisar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      throw new Error(`Error analyzing batch ${i + 1}`);
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

  // Obtém todas as tags
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

  // Mostra loading
  btnTexto.classList.add('d-none');
  btnLoading.classList.remove('d-none');
  analisarBtn.disabled = true;

  try {
    const resultados = await analisarEmLotes(
      artigosIncluidos,
      inclusao,
      exclusao
    );
    const divResultado = document.getElementById('resultadoAnalise');
    divResultado.dataset.resultadosRaw = JSON.stringify(resultados);

    document.getElementById('selectedTitle').style.display = 'none';

    document.getElementById('analysisSection').classList.remove('d-none');
    document.getElementById('analysisSection').classList.add('d-flex');

    mostrarTabelaComResultados(artigosIncluidos, resultados);
  } catch (err) {
    alert('Error: ' + err.message);
    const divResultado = document.getElementById('resultadoAnalise');
    divResultado.innerHTML = `<p class="text-danger">${err.message}</p>`;
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
    return tag.firstChild.textContent.trim();
  });
}

function criarTag(container, texto, cor) {
  const input = container.querySelector('input');

  const tagsAtuais = container.querySelectorAll('.badge');
  const indice = tagsAtuais.length + 1;

  const prefixo = container.id === 'inclusaoBox' ? `IC${indice}` : `EC${indice}`;

  const tag = document.createElement('span');
  tag.className = `badge d-flex align-items-center ${container.id === 'inclusaoBox' ? 'ic-tag' : 'ec-tag'}`;

  tag.innerHTML = `
    ${prefixo}: ${texto}
    <button type="button" class="btn-close btn-close-white ms-2" style="font-size:0.6rem;"></button>
  `;

  tag.querySelector('button').addEventListener('click', () => {
    tag.remove();

    const restantes = container.querySelectorAll('.badge');
    restantes.forEach((t, i) => {
      const newPrefix = container.id === 'inclusaoBox' ? `IC${i + 1}` : `EC${i + 1}`;
      t.childNodes[0].textContent = `${newPrefix}: ${t.textContent.split(': ')[1]}`;
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