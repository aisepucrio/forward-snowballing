const express = require('express');
const app = express();
const port = process.env.PORT || 3000;
const path = require('path');
const { ensureSession } = require('./services/sessionState');

// Middlewares
app.use(express.json());
app.use(ensureSession);

// Importar rotas
const articlesRoutes = require('./routes/articlesRoutes');
app.use('/api/articles', articlesRoutes);

app.use(express.static(path.join(__dirname, 'frontend')));

app.use(express.static(path.join(__dirname, 'frontend', 'html')));
// Novo: Redireciona a rota raiz para o index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'html', 'index.html'));
});

app.get('/analysis.html', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'html', 'analysis.html'));
});

app.get('/criterios.html', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'html', 'criterios.html'));
});


app.listen(port, "0.0.0.0", () => {
  console.log(`✅ Server running at: http://localhost:${port}`);
});

