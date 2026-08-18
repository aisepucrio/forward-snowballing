const TableComponent = (function () {
  
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
      return authors.map(a => (typeof a === 'object' && a?.name ? a.name : a)).join('; ');
    }
    if (typeof authors === 'string') return authors;
    return '-';
  }

  function formatKeywords(keywords) {
    if (!keywords) return '-';
    if (Array.isArray(keywords)) {
      return keywords.length ? keywords.join(', ') : '-';
    }
    return keywords || '-';
  }

  function formatDOILink(doi) {
    if (!doi || doi === '-') return '-';
    const cleanDoi = String(doi).trim();
    const targetUrl = /^https?:\/\//i.test(cleanDoi)
      ? cleanDoi
      : `https://doi.org/${cleanDoi}`;

    return `<a href="${encodeURI(targetUrl)}" target="_blank" rel="noopener noreferrer" style="text-decoration: underline; color: #10b981;">${escapeHtml(cleanDoi)}</a>`;
  }

  function isOpenAccess(value) {
    return value === true || String(value).toLowerCase() === 'true';
  }

  function formatResearchIdentityTags(item) {
    const tags = [
      `<span class="paper-tag">${escapeHtml(item.year || '-')}</span>`,
      `<span class="paper-tag venue-tag">${escapeHtml(item.venue || '-')}</span>`
    ];

    const pagesValue = item.numpages != null ? item.numpages : item.pages;
    if (pagesValue != null && pagesValue !== '-') {
      tags.push(`<span class="paper-tag pages-tag">Pages: ${escapeHtml(String(pagesValue))}</span>`);
    }

    if (isOpenAccess(item.open_access)) {
      tags.push('<span class="paper-tag open-access-tag">Open Access</span>');
    }

    if (item.language && item.language !== '-') {
      tags.push(`<span class="paper-tag language-tag">${escapeHtml(item.language)}</span>`);
    }

    return tags.join('');
  }

  function truncateText(text, maxLength = 140) {
    if (!text || text === '-') return '-';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
  }

  function formatCriteriaBadge(rawValue) {
    const valor = typeof rawValue === 'string' ? rawValue.trim().toLowerCase() : '-';
    if (['sim', 'yes'].includes(valor)) {
      return '<span class="criteria-badge criteria-yes">Yes</span>';
    }
    if (['não', 'nao', 'no'].includes(valor)) {
      return '<span class="criteria-badge criteria-no">No</span>';
    }
    return escapeHtml(rawValue ?? '-');
  }

  function syncExtraHeaders(table, extraColumns, showActions) {
    if (!table) return;
    const theadRow = table.querySelector('thead tr');
    if (!theadRow) return;

    theadRow.querySelectorAll('th[data-dynamic-col]').forEach(th => th.remove());

    if (!extraColumns || extraColumns.length === 0) return;

    const actionsTh = theadRow.querySelector('.col-actions');

    extraColumns.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col.label;
      th.dataset.dynamicCol = 'true';
      th.classList.add('criteria-header');
      if (col.headerClassName) th.classList.add(col.headerClassName);

      if (actionsTh) {
        theadRow.insertBefore(th, actionsTh);
      } else {
        theadRow.appendChild(th);
      }
    });
  }

  // =========================================================================
  // RENDERIZAÇÃO DA TABELA
  // =========================================================================

  /**
   
   *
   * @param {Object} options 
   * @param {string|HTMLElement} options.target 
   * @param {Array} options.data 
   * @param {boolean} [options.showActions=false] 
   * @param {Array} [options.extraColumns=[]]
   * @param {Function} [options.onAction] 
   * @param {Function} [options.onToggleExpand] 
   */
  function render(options = {}) {
    const {
      target,
      data = [],
      showActions = false,
      extraColumns = [],
      onAction = null,
      onToggleExpand = null
    } = options;

    const tbody = typeof target === 'string' ? document.getElementById(target) : target;
    if (!tbody) {
      console.warn('TableComponent: Elemento tbody não encontrado.');
      return;
    }

    const table = tbody.closest('table');
    if (table) {
      const colActionsHeader = table.querySelector('.col-actions');
      if (colActionsHeader) {
        if (showActions) {
          colActionsHeader.classList.remove('d-none');
        } else {
          colActionsHeader.classList.add('d-none');
        }
      }
      syncExtraHeaders(table, extraColumns, showActions);
    }

    const totalColSpan = 4 + (showActions ? 1 : 0) + extraColumns.length;

    if (!data || data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${totalColSpan}" class="text-center text-muted">No records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = '';

    data.forEach((item, index) => {
      const tr = document.createElement('tr');

      const keywordsText = formatKeywords(item.keywords);
      const authorsText = formatAuthors(item.authors);
      const citationsCount = item.citations_count ?? item.citationCount ?? item.cited_by_count ?? '0';

      const abstractTruncated = truncateText(item.abstract, 300);
      const keywordsTruncated = truncateText(keywordsText, 110);

      const hasLongAbstract = item.abstract && item.abstract.length > 300;
      const hasLongKeywords = keywordsText && keywordsText !== '-' && keywordsText.length > 110;

      // Colunas fixas
      tr.innerHTML = `
        <td class="col-identity">
          <div class="paper-doi">
            DOI: ${formatDOILink(item.doi || item.resolved_doi || '-')}
          </div>
          <div class="paper-title fw-semibold">
            ${escapeHtml(item.title || '-')}
          </div>
          <div class="paper-authors text-muted mt-1">
            ${escapeHtml(authorsText)}
          </div>
          <div class="paper-tags d-flex flex-wrap gap-1 mt-2">
            ${formatResearchIdentityTags(item)}
          </div>
        </td>

        <td class="col-abstract">
          <div class="abstract-text ${item.abstractExpanded ? 'expanded' : ''}">
            ${item.abstractExpanded ? escapeHtml(item.abstract || '-') : escapeHtml(abstractTruncated)}
          </div>
          ${
            hasLongAbstract
              ? `<span class="read-more abstract-read-more" role="button" style="cursor:pointer; color:#0b6b43; font-weight:600; font-size:0.8rem;">
                  ${item.abstractExpanded ? 'READ LESS' : 'READ MORE'}
                </span>`
              : ''
          }
        </td>

        <td class="col-keywords">
          <div class="keywords-text ${item.keywordsExpanded ? 'expanded' : ''}">
            ${item.keywordsExpanded ? escapeHtml(keywordsText) : escapeHtml(keywordsTruncated)}
          </div>
          ${
            hasLongKeywords
              ? `<span class="read-more keywords-read-more" role="button" style="cursor:pointer; color:#0b6b43; font-weight:600; font-size:0.8rem;">
                  ${item.keywordsExpanded ? 'READ LESS' : 'READ MORE'}
                </span>`
              : ''
          }
        </td>

        <td class="col-citations text-center">
          <div class="citation-box d-inline-flex align-items-center gap-2">
            <div class="citation-dot" style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;"></div>
            <div>
              <div class="citation-number fw-bold">${escapeHtml(String(citationsCount))}</div>
            </div>
          </div>
        </td>
      `;

      extraColumns.forEach(col => {
        const td = document.createElement('td');
        td.className = col.className || 'text-center';
        td.innerHTML = typeof col.render === 'function' ? col.render(item, index) : '-';
        tr.appendChild(td);
      });

      if (showActions) {
        const tdActions = document.createElement('td');
        tdActions.className = 'col-actions text-center';
        tdActions.innerHTML = `
          <div class="action-buttons">
            <button type="button" class="btn-action include-btn ${item.selecionado === 'incluir' ? 'active' : ''}" title="Include">
              <i class="bi bi-check-lg"></i>
            </button>
            <button type="button" class="btn-action exclude-btn ${item.selecionado === 'excluir' ? 'active' : ''}" title="Exclude">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
        `;
        tr.appendChild(tdActions);
      }

      const btnAbstract = tr.querySelector('.abstract-read-more');
      if (btnAbstract) {
        btnAbstract.addEventListener('click', () => {
          item.abstractExpanded = !item.abstractExpanded;
          if (typeof onToggleExpand === 'function') {
            onToggleExpand(item, 'abstract', index);
          } else {
            render(options);
          }
        });
      }

      const btnKeywords = tr.querySelector('.keywords-read-more');
      if (btnKeywords) {
        btnKeywords.addEventListener('click', () => {
          item.keywordsExpanded = !item.keywordsExpanded;
          if (typeof onToggleExpand === 'function') {
            onToggleExpand(item, 'keywords', index);
          } else {
            render(options);
          }
        });
      }

      if (showActions && typeof onAction === 'function') {
        const includeBtn = tr.querySelector('.include-btn');
        const excludeBtn = tr.querySelector('.exclude-btn');

        if (includeBtn) {
          includeBtn.addEventListener('click', () => {
            const newStatus = item.selecionado === 'incluir' ? null : 'incluir';
            item.selecionado = newStatus;
            onAction(item, newStatus, index);
          });
        }

        if (excludeBtn) {
          excludeBtn.addEventListener('click', () => {
            const newStatus = item.selecionado === 'excluir' ? null : 'excluir';
            item.selecionado = newStatus;
            onAction(item, newStatus, index);
          });
        }
      }

      tbody.appendChild(tr);
    });
  }

  return {
    render,
    escapeHtml,
    formatAuthors,
    formatKeywords,
    formatDOILink,
    formatResearchIdentityTags,
    formatCriteriaBadge,
    truncateText,
    isOpenAccess
  };
})();

if (typeof window !== 'undefined') {
  window.TableComponent = TableComponent;
}