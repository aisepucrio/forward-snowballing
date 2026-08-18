document.addEventListener("DOMContentLoaded", () => {
  const footerContainer = document.getElementById("footer-component");
  if (footerContainer) {
    fetch("components/footer/footer.html")
      .then(response => {
        if (!response.ok) {
          throw new Error("Erro ao carregar o footer.");
        }
        return response.text();
      })
      .then(html => {
        footerContainer.innerHTML = html;
      })
      .catch(error => console.error("Erro no componente de footer:", error));
  }
});