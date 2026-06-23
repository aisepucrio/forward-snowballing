const express = require('express');
const app = express();
const port = process.env.PORT || 3000;
const path = require('path');
const { ensureSession } = require('./services/sessionState');

// Middlewares
app.use(express.json());
app.use(ensureSession);
app.use((req, res, next) => {
  if (/\.(html|css|js)$/i.test(req.path) || req.path === '/') {
    res.setHeader('Cache-Control', 'no-store');
  }
  next();
});

// Importar rotas
const articlesRoutes = require('./routes/articlesRoutes');
app.use('/api/articles', articlesRoutes);

// Novo: Serve arquivos estáticos da pasta "frontend"
app.use(express.static(path.join(__dirname, 'frontend')));

// Novo: Redireciona a rota raiz para o index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});



const server = app.listen(port, "0.0.0.0", () => {
  console.log(`✅ Server running at: http://localhost:${port}`);
});

server.requestTimeout = 10 * 60 * 1000;
server.headersTimeout = 10 * 60 * 1000 + 1000;
