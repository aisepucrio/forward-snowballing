const express = require('express');
const app = express();
const port = process.env.PORT || 3000;
const path = require('path');

// Middlewares
app.use(express.json());

// Importar rotas
const articlesRoutes = require('./routes/articlesRoutes');
app.use('/api/articles', articlesRoutes);

// Novo: Serve arquivos estáticos da pasta "frontend"
app.use(express.static(path.join(__dirname, 'frontend')));

// Novo: Redireciona a rota raiz para o index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});



app.listen(port, () => {
  console.log(`✅ Server running at: http://localhost:${port}`);
});

