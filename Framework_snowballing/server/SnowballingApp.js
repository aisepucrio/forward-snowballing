const express = require('express');
const path = require('path');
const { ensureSession } = require('../services/sessionState');
const articlesRoutes = require('../routes/articlesRoutes');

class SnowballingApp {
  constructor({ port = process.env.PORT || 3000, frontendDir = path.join(__dirname, '..', 'frontend') } = {}) {
    this.port = port;
    this.frontendDir = frontendDir;
    this.htmlDir = path.join(frontendDir, 'html');
    this.app = express();
  }

  build() {
    this.registerMiddleware();
    this.registerRoutes();
    this.registerStaticFiles();
    return this.app;
  }

  start() {
    const server = this.build().listen(this.port, '0.0.0.0', () => {
      console.log(`✅ Server running at: http://localhost:${this.port}`);
    });

    server.requestTimeout = 10 * 60 * 1000;
    server.headersTimeout = 10 * 60 * 1000 + 1000;
    return server;
  }

  registerMiddleware() {
    this.app.use(express.json());
    this.app.use(ensureSession);
    this.app.use((req, res, next) => {
      if (/\.(html|css|js)$/i.test(req.path) || req.path === '/') {
        res.setHeader('Cache-Control', 'no-store');
      }
      next();
    });
  }

  registerRoutes() {
    this.app.use('/api/articles', articlesRoutes);
  }

  registerStaticFiles() {
    this.app.use(express.static(this.frontendDir));
    this.app.use(express.static(this.htmlDir));
    this.app.get('/', (req, res) => {
      res.sendFile(path.join(this.htmlDir, 'index.html'));
    });
  }
}

module.exports = {
  SnowballingApp,
};
