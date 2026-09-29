    function escapeHtml(text) {
      if (text === null || text === undefined) return '-';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function formatAuthors(authors) {
      if (!authors) return '-';
      if (Array.isArray(authors)) {
        if (authors.length === 0) return '-';
        return authors.map(a => a?.name || a).join('; ');
      }
      if (typeof authors === 'string') return authors;
      return '-';
    }

    function mostrarResultado(artigo) {
      const resultadoEl = document.getElementById('resultado');
      if (!resultadoEl) return;

      if (!artigo || !artigo.title) {
        resultadoEl.innerHTML = '<p class="text-muted">Seed article data not found.</p>';
        return;
      }

      const authors = formatAuthors(artigo.authors);
      const doiToShow = artigo.resolved_doi || artigo.input_doi || artigo.doi || '-';

      resultadoEl.innerHTML = `
      <div class="table-wrapper mb-4">
        <div class="table-topbar">
          <div class="table-info">
            <span class="table-title">Seed Paper</span>
          </div>
        </div>

        <table class="custom-table">
          <thead>
            <tr>
              
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <div class="paper-doi">
                  DOI: ${escapeHtml(doiToShow)}
                </div>
                <div class="paper-title">
                  ${escapeHtml(artigo.title || '-')}
                </div>
                ${escapeHtml(authors)}
                <div class="paper-meta">
                  <div class="paper-tags">
                    <span class="paper-tag">
                      ${escapeHtml(artigo.year || '-')}
                    </span>
                    <span class="paper-tag venue-tag">
                      ${escapeHtml(artigo.venue || '-')}
                    </span>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      `;
    }

    const totalArtigosEl = document.getElementById('total-artigos');
    const totalVenueEl = document.getElementById('total-venue');

    function normalizeArticles(data) {
      return data.map(item => ({
        paperId: item.paperId || '',
        title: item.title || "Untitled",
        abstract: item.abstract || "No abstract available",
        year: item.year || "N/A",
        venue: item.venue || (item.publicationVenue && item.publicationVenue.name) || "N/A",
        selecionado: item.selecionado || null,
        open_access: item.open_access !== undefined ? item.open_access : null,
        citations_count: parseInt(item.citations_count || 0, 10)
      }));
    }

    const countBy = (arr, key) => arr.reduce((acc, item) => {
      const val = item[key] || "N/A";
      acc[val] = (acc[val] || 0) + 1;
      return acc;
    }, {});

    function fillList(el, obj) {
      if (!el) return;
      el.innerHTML = '';
      Object.entries(obj).sort().forEach(([key, val]) => {
        const li = document.createElement('li');
        li.textContent = `${key}: ${val}`;
        el.appendChild(li);
      });
    }

    const stopwords = new Set([
      'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves',
      'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their',
      'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
      'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an',
      'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about',
      'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up',
      'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
      'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
      'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don',
      'should', 'now', 'using', 'used', 'use', 'based', 'results', 'paper', 'study', 'approach', 'method', 'analysis'
    ]);

    function processarTextoPLN(artigos) {
      const frequenciaPalavras = {};

      artigos.forEach(artigo => {
        const titulo = artigo.title || "";
        const abstract = (artigo.abstract && artigo.abstract !== "No abstract available") ? artigo.abstract : "";
        
        let keywords = "";
        if (artigo.keywords) {
          if (Array.isArray(artigo.keywords)) {
            keywords = artigo.keywords.join(" ");
          } else if (typeof artigo.keywords === 'string') {
            keywords = artigo.keywords;
          }
        }

        const textoCompleto = `${titulo} ${keywords} ${abstract}`;
        
        if (!textoCompleto.trim()) return;

        const palavras = textoCompleto.toLowerCase()
          .replace(/[^\w\s-]/g, '')
          .split(/[\s]+/);

        palavras.forEach(palavra => {
          if (palavra.length <= 2 || stopwords.has(palavra) || !isNaN(palavra)) return;

          frequenciaPalavras[palavra] = (frequenciaPalavras[palavra] || 0) + 1;
        });
      });

      return Object.entries(frequenciaPalavras)
        .map(([text, size]) => ({ text, size }))
        .sort((a, b) => b.size - a.size)
        .slice(0, 100);
    }

    let nuvemResizeTimeout;

    function gerarNuvemPalavras(artigos) {
      const container = document.getElementById('word-cloud');
      if (!container) return;
      
      container.innerHTML = '';

      const palavrasDados = processarTextoPLN(artigos);
      if (palavrasDados.length === 0) {
        container.innerHTML = '<p class="text-muted p-4">No abstract data available to generate word cloud.</p>';
        return;
      }

      const largura = container.offsetWidth || 800;
      const altura = largura < 576 ? 260 : 380; 

      let fonteMin = 14;
      let fonteMax = 52;

      if (largura < 576) {
        fonteMin = 10;
        fonteMax = 24;
      } else if (largura < 992) {
        fonteMin = 12;
        fonteMax = 36;
      }

      const maxSize = d3.max(palavrasDados, d => d.size);
      const minSize = d3.min(palavrasDados, d => d.size);
      
      const escalaFonte = d3.scaleLinear()
        .domain([minSize, maxSize])
        .range([fonteMin, fonteMax]);

      const coresNuvem = ['#5D8AA8', '#367588', '#2F4F4F', '#3F7CAC', '#264348', '#2C5F71', '#5B8D89', '#176D6D'];

      const layout = d3.layout.cloud()
        .size([largura, altura])
        .words(palavrasDados.map(d => ({ text: d.text, size: escalaFonte(d.size) })))
        .padding(5)
        .rotate(() => (Math.random() > 0.75 ? 90 : 0))
        .font("Poppins, sans-serif")
        .fontSize(d => d.size)
        .on("end", desenharNuvem);

      layout.start();

      function desenharNuvem(words) {
        const svg = d3.select("#word-cloud")
          .append("svg")
          .attr("viewBox", `0 0 ${largura} ${altura}`)
          .attr("width", "100%")
          .attr("height", "100%")
          .attr("preserveAspectRatio", "xMidYMid meet")
          .append("g")
          .attr("transform", `translate(${largura / 2},${altura / 2})`);

        svg.selectAll("text")
          .data(words)
          .enter().append("text")
          .style("font-size", d => `${d.size}px`)
          .style("font-family", "Poppins, sans-serif")
          .style("font-weight", "600")
          .style("fill", () => coresNuvem[Math.floor(Math.random() * coresNuvem.length)])
          .attr("text-anchor", "middle")
          .attr("transform", d => `translate(${d.x}, ${d.y}) rotate(${d.rotate})`)
          .text(d => d.text)
          .on("mouseover", function() { d3.select(this).style("opacity", "0.7"); })
          .on("mouseout", function() { d3.select(this).style("opacity", "1"); });
      }

      window.removeEventListener('resize', forcarRecalculoNuvem);
      window.addEventListener('resize', forcarRecalculoNuvem);

      function forcarRecalculoNuvem() {
        clearTimeout(nuvemResizeTimeout);
        nuvemResizeTimeout = setTimeout(() => {
          const novaLargura = document.getElementById('word-cloud')?.offsetWidth;
          if (novaLargura && novaLargura !== largura) {
            gerarNuvemPalavras(artigos);
          }
        }, 250);
      }
    }

    function atualizarResumoEgraficos(artigos) {
      const porAno = countBy(artigos, 'year');
      const porVenueTotal = countBy(artigos, 'venue');

      const totalOpenAccessEl = document.getElementById('total-open-access');
      const mostCitedEl = document.getElementById('most-cited');
      const mostCitedAuthorsEl = document.getElementById('most-cited-authors');

      const totalOpenAccess = artigos.filter(artigo => 
        artigo.open_access === true || 
        artigo.open_access === 'true'
      ).length;

      if (artigos.length === 0) {
        if (mostCitedEl) mostCitedEl.innerHTML = "<p class='m-0 text-white-50'>No articles selected.</p>";
        if (mostCitedAuthorsEl) mostCitedAuthorsEl.innerHTML = "<p class='m-0 text-white-50'>No articles selected.</p>";
      } 
      
      else {
        if (mostCitedEl) {
          const topCitados = [...artigos]
            .sort((a, b) => b.citations_count - a.citations_count)
            .slice(0, 3);
          
          let listaHTML = '<ol class="ps-3 m-0" style="color: #000;">';
          topCitados.forEach(artigo => {
            listaHTML += `
              <li class="mb-2">
                ${escapeHtml(artigo.title)}
                <strong style="color: #000;">(${artigo.citations_count} citations)</strong> 
              </li>`;
          });
          listaHTML += '</ol>';
          mostCitedEl.innerHTML = listaHTML;
        }

        if (mostCitedAuthorsEl) {
          const citacoesAutores = {};

          artigos.forEach(artigo => {
            const numCitations = artigo.citations_count || 0;
            const autoresOriginais = dadosOriginaisDoArtigo(artigo) || []; 
            
            if (Array.isArray(autoresOriginais)) {
              autoresOriginais.forEach(autor => {
                const nomeAutor = typeof autor === 'string' ? autor : autor?.name;
                if (nomeAutor && nomeAutor !== '-') {
                  citacoesAutores[nomeAutor] = (citacoesAutores[nomeAutor] || 0) + numCitations;
                }
              });
            }
          });

        const topAutores = Object.entries(citacoesAutores)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3);

          if (topAutores.length === 0) {
            mostCitedAuthorsEl.innerHTML = "<p class='m-0 text-muted'>N/A</p>";
          } 
          
          else {
            let listaAutoresHTML = '<ol class="ps-3 m-0" style="color: #000;">';
            topAutores.forEach(([autor, citacoes]) => {
              listaAutoresHTML += `
                <li class="mb-2">
                  ${escapeHtml(autor)}
                  <strong style="color: #000;">(${citacoes} total citations)</strong> 
                </li>`;
            });
            listaAutoresHTML += '</ol>';
            mostCitedAuthorsEl.innerHTML = listaAutoresHTML;
          }
        }
      }

      function dadosOriginaisDoArtigo(artigoNormalizado) {
        try {
          const dadosOriginais = JSON.parse(window.name || '[]');
          const original = dadosOriginais.find(a => a.paperId === artigoNormalizado.paperId || a.title === artigoNormalizado.title);
          return original ? original.authors : null;
        } catch(e) {
          return null;
        }
      }

      totalArtigosEl.textContent = artigos.length;
      totalVenueEl.textContent = Object.keys(porVenueTotal).length;
      if (totalOpenAccessEl) {
        totalOpenAccessEl.textContent = totalOpenAccess;
      }

      if (window.chartAno) window.chartAno.destroy();
      if (window.chartVenue) window.chartVenue.destroy();

      const corNormal = '#000000';
      const corDestacada = '#000000';
      const corOpaca = 'rgba(0, 0, 0, 0.3)';
      
      let anosSelecionados = Object.keys(porAno);

      function filtrarArtigosPorAnosSelecionados() {
        return artigos.filter(artigo => anosSelecionados.includes(artigo.year.toString()));
      }

      function atualizarGraficoVenues() {
        const artigosFiltrados = filtrarArtigosPorAnosSelecionados();
        const venuesFiltrados = countBy(artigosFiltrados, 'venue');
        
        if (window.chartVenue) {
          window.chartVenue.destroy();
        }
        
        const cores_hex = [
          '#5D8AA8', '#367588', '#2F4F4F', '#3F7CAC', '#264348', '#004242', '#2C5F71', '#5B8D89', '#628B7B',
          '#436D61', '#1D475C', '#78B2AB', '#509C87', '#47836C', '#2D7452', '#33596F', '#006B5E', '#1F4F4F',
          '#176D6D', '#1A5B6E', '#2E6B6B', '#008080', '#42736E', '#3B7A70', '#206B5E', '#3B6D6D', '#1E5945', '#236B54'
        ];

        window.chartVenue = new Chart(document.getElementById('graficoVenue'), {
          type: 'pie',
          data: {
            labels: Object.keys(venuesFiltrados),
            datasets: [{ 
              data: Object.values(venuesFiltrados), 
              backgroundColor: cores_hex.slice(0, Object.keys(venuesFiltrados).length)
            }]
          },
          options: { 
            plugins: { legend: { position: 'right' } },
            onClick: (event, elements) => {
              if (elements && elements.length > 0) {
                const elementIndex = elements[0].index;
                const venue = Object.keys(venuesFiltrados)[elementIndex];
                const quantidade = Object.values(venuesFiltrados)[elementIndex];
              }
            }
          }
        });
        
      }

      function atualizarCoresBarras(anosSelecionados) {
        if (!window.chartAno) return;
        
        if (!anosSelecionados || anosSelecionados.length === 0) {
          console.error('anosSelecionados inválido');
          return;
        }
        
        const anos = Object.keys(porAno);
        const novasCores = anos.map(ano => {
          if (anosSelecionados.includes(ano)) {
            return corDestacada;
          } else {
            return corOpaca;
          }
        });
        
        window.chartAno.data.datasets[0].backgroundColor = novasCores;
        window.chartAno.update();
        
        atualizarGraficoVenues();
      }

      function todosAnosSelecionados() {
        return anosSelecionados.length === Object.keys(porAno).length;
      }

      function atualizarCheckbox() {
        const checkbox = document.getElementById('checkbox');
        if (checkbox) {
          checkbox.checked = todosAnosSelecionados();
        }
      }

      window.chartAno = new Chart(document.getElementById('graficoAno'), {
        type: 'bar',
        data: {
          labels: Object.keys(porAno),
          datasets: [{ 
            data: Object.values(porAno), 
            backgroundColor: Object.keys(porAno).map(() => corNormal)
          }]
        },
        options: { 
          plugins: { legend: { display: false } }, 
          scales: { y: { beginAtZero: true } },
          onClick: (event, elements) => {
            if (elements && elements.length > 0) {
              const elementIndex = elements[0].index;
              const ano = Object.keys(porAno)[elementIndex];
              const quantidade = Object.values(porAno)[elementIndex];

              const index = anosSelecionados.indexOf(ano);
              
              if (index === -1) {
                anosSelecionados.push(ano);
              } else {
                if (anosSelecionados.length > 1) {
                  anosSelecionados.splice(index, 1);
                } else {
                  alert('At least one year must be selected.');
                  return;
                }
              }
              
              anosSelecionados.sort();
                            
              atualizarCoresBarras(anosSelecionados);
              
              atualizarCheckbox();
            }
          }
        }
      });

      setTimeout(() => {
        const checkbox = document.getElementById('checkbox');
        if (!checkbox) {
          console.error('Checkbox não encontrado');
          return;
        }
        
        const novoCheckbox = checkbox.cloneNode(true);
        checkbox.parentNode.replaceChild(novoCheckbox, checkbox);
        
        novoCheckbox.checked = true;
        
        novoCheckbox.addEventListener('change', function(e) {
          if (this.checked) {
            anosSelecionados = Object.keys(porAno);
          } else {            
            const todosAnos = Object.keys(porAno);
            anosSelecionados = [todosAnos[0]];
            
            this.checked = false;
          }
          
          atualizarCoresBarras(anosSelecionados);
        });
      }, 100);
      
      atualizarCoresBarras(anosSelecionados);
      gerarNuvemPalavras(artigos);
    }

    function carregarArtigosLocal() {
      const seedDataStorage = localStorage.getItem('seedPaperData');
      
      if (seedDataStorage) {
        try {
          const artigoSemente = JSON.parse(seedDataStorage);
          mostrarResultado(artigoSemente);
        } catch (e) {
          console.error("Error parsing Seed Paper data:", e);
          document.getElementById('resultado').innerHTML = '<p class="text-muted">Error loading seed article data.</p>';
        }
      } else {
        if (window.name) {
          try {
            const dados = JSON.parse(window.name);
            if (dados && dados.length > 0) {
              const seedRef = dados.find(a => a.isSeed || a.seed === true) || dados[0];
              mostrarResultado(seedRef);
            }
          } catch(e) {
            document.getElementById('resultado').innerHTML = '<p class="text-muted">Seed article data not found.</p>';
          }
        }
      }

      if (!window.name) {
        alert('No articles found for screening. Please return to the home page and try a new search.');
        return;
      }
      
      try {
        const dados = JSON.parse(window.name);
        const artigos = normalizeArticles(dados.filter(a => a.selecionado === 'incluir'));
        atualizarResumoEgraficos(artigos);
      } catch (e) {
        alert('Error loading screening data: ' + e.message);
      }
    }

    function salvarPesquisaAtual(valor) {
      localStorage.setItem('ultimaPesquisaSnowMap', valor);
    }

    function buscarArtigoNavbar() {

      const input = document.getElementById('navbarSearchInput');

      const valor = input.value.trim();

      if (!valor) {
        alert('Please enter a DOI or title.');
        return;
      }

      salvarPesquisaAtual(valor);

      localStorage.setItem(
        'executarBuscaSnowMap',
        'true'
      );

      window.location.href =
        `index.html?search=${encodeURIComponent(valor)}`;
    }

    document.addEventListener('DOMContentLoaded', () => {

      const valorSalvo = localStorage.getItem('ultimaPesquisaSnowMap');

      const navbarInput = document.getElementById('navbarSearchInput');

      if (valorSalvo && navbarInput) {
        navbarInput.value = valorSalvo;
      }
    });

    document.addEventListener('DOMContentLoaded', carregarArtigosLocal);

    const linkCriteriosEl = document.getElementById('linkCriterios');
    if (linkCriteriosEl) {
      linkCriteriosEl.addEventListener('click', function (e) {
        e.preventDefault();
        try {
          const dados = JSON.parse(window.name || '[]');
          const selecionados = dados.filter(a => a.selecionado === 'incluir');
          window.name = JSON.stringify(selecionados);
          window.location.href = 'criterios.html';
        } catch (e) {
          alert('Error preparing data for criteria screen:  ' + e.message);
        }
      });
    }

   document.getElementById('btn-exportar-pdf').addEventListener('click', function () {
      const elemento = document.querySelector('main.container');
      
      this.style.display = 'none';
      const checkboxContainer = document.querySelector('.alinhamento-checkbox');
      if (checkboxContainer) checkboxContainer.style.display = 'none';

      const nuvemPalavras = document.getElementById('word-cloud');
      if (nuvemPalavras) nuvemPalavras.style.display = 'none';

      let tituloWordCloud = null;
      document.querySelectorAll('h3, h4, p, div').forEach(el => {
        if (el.textContent.trim() === 'Word Cloud') {
          tituloWordCloud = el;
          tituloWordCloud.style.display = 'none';
        }
      });

      if (!document.getElementById('fonte-poppins-pdf')) {
        const linkFonte = document.createElement('link');
        linkFonte.id = 'fonte-poppins-pdf';
        linkFonte.rel = 'stylesheet';
        linkFonte.href = 'https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap';
        document.head.appendChild(linkFonte);
      }

      const cabecalhoDocs = document.createElement('div');
      cabecalhoDocs.id = 'cabecalho-pdf-docs';
      cabecalhoDocs.innerHTML = `
        <div style="padding-bottom: 12px; margin-bottom: 30px; font-family: 'Poppins', sans-serif; box-sizing: border-box;">
          <table style="width: 100%; border-collapse: collapse; border: none; margin: 0; padding: 0;">
            <tr>
              <td style="vertical-align: middle; border: none; padding: 0; text-align: left;">
                <h1 style="margin: 0; color: #000000; font-size: 24px; letter-spacing: -0.5px;">SnowMap — Data Analysis Report</h1>
                <p style="margin: 4px 0 0 0; color: #2d3748; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">AISE Lab (Artificial Intelligence and Software Engineering)</p>
              </td>
              <td style="text-align: right; vertical-align: middle; border: none; padding: 0; color: #2d3748; font-size: 11px; line-height: 1.4;">
                <div><strong>Issue Date:</strong> ${new Date().toLocaleDateString('pt-BR')}</div>
                <div><strong>Document Type:</strong> Systematic Review</div>
              </td>
            </tr>
          </table>
        </div>
      `;
      elemento.insertBefore(cabecalhoDocs, elemento.firstChild);

      const estiloImpressao = document.createElement('style');
      estiloImpressao.id = 'estilo-pdf-linear-absoluto';
      estiloImpressao.innerHTML = `
        * {
          box-sizing: border-box !important;
        }

        main.container {
          font-family: 'Poppins', sans-serif !important;
          color: #000000 !important;
          background: #ffffff !important;
          padding: 0 !important;
          margin: 0 !important;
          width: 100% !important;
          max-width: 100% !important;
          overflow: hidden !important;
        }

        .row, .cards-resumo-row, .d-flex {
          display: block !important;
          width: 100% !important;
          clear: both !important;
          float: none !important;
          margin: 0 !important;
          padding: 0 !important;
        }
        
        h3.titulo, h3.subtitulo {
          font-family: 'Poppins', sans-serif !important;
          font-size: 16px !important;
          color: #000000 !important;
          border-left: none !important;
          padding-left: 0 !important;
          margin-top: 25px !important;
          margin-bottom: 15px !important;
          font-weight: bold !important;
          text-transform: none !important;
          page-break-after: avoid !important;
          break-after: avoid !important;
        }

        h4 {
          font-family: 'Poppins', sans-serif !important;
          font-size: 13px !important;
          color: #2d3748 !important;
          margin-top: 20px !important;
          margin-bottom: 10px !important;
          font-weight: bold !important;
          page-break-after: avoid !important;
          break-after: avoid !important;
        }

        .col-md-6, .col-md-4, .col-12 {
          display: block !important;
          width: 100% !important;
          max-width: 100% !important;
          float: none !important;
          margin-bottom: 12px !important;
          padding: 0 !important;
        }

        .card-resumo, .quadro-conteudo {
          display: block !important;
          width: 100% !important;
          background: #ffffff !important;
          border: none !important;
          border-bottom: 1px solid #e2e8f0 !important;
          box-shadow: none !important;
          padding: 8px 0 !important;
          margin: 0 !important;
          border-radius: 0 !important;
          height: auto !important;
          min-height: 0 !important;
          page-break-inside: avoid !important;
          break-inside: avoid !important;
        }

        .card-resumo h5 {
          font-size: 12px !important;
          color: #4a5568 !important;
          margin: 0 0 2px 0 !important;
          font-weight: bold !important;
        }

        .card-resumo p {
          font-size: 15px !important;
          color: #000000 !important;
          font-weight: bold !important;
          margin: 0 !important;
        }

        .table-wrapper {
          border: 1px solid #cbd5e0 !important;
          border-radius: 8px !important;
          margin-bottom: 25px !important;
          width: 100% !important;
          overflow: hidden !important;
          page-break-inside: avoid !important;
          break-inside: avoid !important;
          background: #ffffff !important;
        }

        .table-topbar {
          background: #f3f4f6 !important;
          border-bottom: 1px solid #cbd5e0 !important;
          padding: 8px 12px !important;
        }

        .table-title {
          font-size: 11px !important;
          font-weight: bold !important;
          color: #2b2d42 !important;
          text-transform: uppercase;
        }

        .custom-table {
          width: 100% !important;
          border-collapse: collapse !important;
        }

        .custom-table td {
          padding: 12px !important;
          color: #2d3748 !important;
          font-size: 11px !important;
          line-height: 1.5 !important;
        }

        .paper-doi {
          color: #2d3748 !important;
          font-size: 10px !important;
          margin-bottom: 4px !important;
        }

        .paper-title {
          font-size: 14px !important;
          font-weight: bold !important;
          color: #000000 !important;
          margin-bottom: 6px !important;
        }

        .paper-tags {
          margin-top: 8px !important;
        }

        .paper-tag {
          background: #f3f4f6 !important;
          color: #2d3748 !important;
          padding: 3px 8px !important;
          border: 1px solid #f3f4f6 !important;
          border-radius: 4px !important;
          font-size: 10px !important;
          font-weight: 600 !important;
          display: inline-block !important;
          margin-right: 6px !important;
        }

        #most-cited, #most-cited-authors {
          font-size: 11px !important;
          color: #2d3748 !important;
          line-height: 1.5 !important;
        }
        
        #most-cited ol, #most-cited-authors ol {
          padding-left: 18px !important;
          margin: 4px 0 0 0 !important;
        }

        #most-cited li, #most-cited-authors li {
          margin-bottom: 6px !important;
        }

        canvas {
          display: block !important;
          width: 100% !important;
          max-width: 320px !important;
          height: auto !important;
          margin: 10px auto !important;
          page-break-inside: avoid !important;
          break-inside: avoid !important;
          filter: grayscale(100%) !important;
        }
      `;
      document.head.appendChild(estiloImpressao);

      const configuracoes = {
        margin:       [20, 15, 20, 15],
        filename:     'SnowMap-Data-Analysis-Report.pdf',
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { 
          scale: 2,
          useCORS: true, 
          logging: false,
          letterRendering: true,
          scrollY: 0,
          scrollX: 0,
          background: '#ffffff',
          windowWidth: elemento.scrollWidth
        },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak:    { mode: ['css', 'legacy'] }
      };

      html2pdf().set(configuracoes).from(elemento).save().then(() => {
        this.style.display = 'block';
        if (checkboxContainer) checkboxContainer.style.display = 'block';
        
        if (nuvemPalavras) nuvemPalavras.style.display = 'block';
        if (tituloWordCloud) tituloWordCloud.style.display = '';

        const cabecalhoRemover = document.getElementById('cabecalho-pdf-docs');
        if (cabecalhoRemover) cabecalhoRemover.remove();

        const estiloRemover = document.getElementById('estilo-pdf-linear-absoluto');
        if (estiloRemover) estiloRemover.remove();
      }).catch(err => {
        console.error("Error generating PDF:", err);
        this.style.display = 'block';
        if (checkboxContainer) checkboxContainer.style.display = 'block';
        
        if (nuvemPalavras) nuvemPalavras.style.display = 'block';
        if (tituloWordCloud) tituloWordCloud.style.display = '';

        const cabecalhoRemover = document.getElementById('cabecalho-pdf-docs');
        if (cabecalhoRemover) cabecalhoRemover.remove();

        const estiloRemover = document.getElementById('estilo-pdf-linear-absoluto');
        if (estiloRemover) estiloRemover.remove();
      });
    });
 