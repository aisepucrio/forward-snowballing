function injetarNavbar() {
  const navbarContainer = document.getElementById("navbar-component");
  
  if (navbarContainer) {
    navbarContainer.innerHTML = `
      <nav class="navbar navbar-expand-lg fixed-top navbar-custom">
        <div class="container-fluid navbar-inner">

          <a class="navbar-brand d-flex align-items-center gap-2" href="index.html" id="navbarSnowballing">
            <img src="/images/logo-snowballing.png" class="logo-nav" alt="Logo SnowMap">
            <span class="brand-text">SnowMap</span>
          </a>

          <form id="navbarSearchForm" class="navbar-search d-none" onsubmit="if(typeof buscarArtigoNavbar === 'function') { buscarArtigoNavbar(); } return false;">
            <i class="bi bi-search"></i>
            <input type="text" id="navbarSearchInput" placeholder="Enter DOI or Title (e.g., 10.1145/3025453.3025795)">
            <button type="submit">Search</button>
          </form>

          <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
          </button>

          <div class="collapse navbar-collapse justify-content-end" id="navbarNav">
            <div id="navbarModeToggle" class="d-none me-3">
              <div class="btn-group" role="group">
                <input type="radio" class="btn-check" name="navbarSnowballMode" id="navbarModeForward" value="forward" checked>
                <label class="btn btn-outline-success btn-sm px-3" for="navbarModeForward">
                  <i class="bi bi-arrow-up-right-circle me-1"></i> Citations
                </label>
                <input type="radio" class="btn-check" name="navbarSnowballMode" id="navbarModeBackward" value="backward">
                <label class="btn btn-outline-success btn-sm px-3" for="navbarModeBackward">
                  <i class="bi bi-arrow-down-left-circle me-1"></i> References
                </label>
              </div>
            </div>
            <ul class="navbar-nav gap-2">
              <li class="nav-item">
                <a class="nav-link btn-nav-custom" href="analysis.html">Data Analysis</a>
              </li>
              <li class="nav-item">
                <a class="nav-link btn-nav-custom" href="criterios.html">Criteria Applications</a>
              </li>
            </ul>
          </div>
        </div>
      </nav>
    `;

    const radios = document.querySelectorAll('input[name="navbarSnowballMode"]');
    radios.forEach(radio => {
      radio.addEventListener('change', () => {
        const mainRadio = document.getElementById(radio.value === 'forward' ? 'modeForward' : 'modeBackward');
        if (mainRadio) mainRadio.checked = true;
        if (typeof trocarModo === 'function' && (window.forwardData !== null || window.backwardData !== null)) {
          trocarModo();
        }
      });
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injetarNavbar);
} else {
  injetarNavbar();
}