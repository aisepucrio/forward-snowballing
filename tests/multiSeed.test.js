const test = require('node:test');
const assert = require('node:assert/strict');

const { ArticleSearchService } = require('../services/articleSearchService');
const { parseProgressLine } = require('../services/searchProgress');

function fakeRunner(result = { multi_seed: true, seeds: [] }) {
  const calls = [];
  return {
    calls,
    runJsonScript: async (script, options) => {
      calls.push({ script, options });
      return result;
    },
  };
}

test('searchMulti envia as seeds limpas para run_multi.py pelo stdin', async () => {
  const runner = fakeRunner();
  const service = new ArticleSearchService({ pythonRunner: runner });

  // writeOutput grava em sessions/<id>; um id próprio isola o teste.
  await service.searchMulti({
    sessionId: 'test-multi-seed',
    seeds: [{ type: 'DOI', value: ' 10.1000/abc ' }, { type: 'title', value: 'A title' }],
  });

  assert.equal(runner.calls.length, 1);
  assert.equal(runner.calls[0].script, 'run_multi.py');
  assert.deepEqual(runner.calls[0].options.input, {
    seeds: [{ type: 'doi', value: '10.1000/abc' }, { type: 'title', value: 'A title' }],
  });
  assert.ok(runner.calls[0].options.maxOutputBytes > 10 * 1024 * 1024);
});

test('searchMulti recusa entrada inválida com 400 sem chamar o Python', async () => {
  const runner = fakeRunner();
  const service = new ArticleSearchService({ pythonRunner: runner });
  const tooMany = Array.from({ length: 21 }, (_, i) => ({ type: 'title', value: `Paper ${i}` }));

  const invalid = [
    undefined,
    [],
    tooMany,
    [{ type: 'isbn', value: '123' }],
    [{ type: 'doi', value: '   ' }],
  ];

  for (const seeds of invalid) {
    await assert.rejects(
      service.searchMulti({ sessionId: 'test-multi-seed', seeds }),
      (err) => err.statusCode === 400,
    );
  }
  assert.equal(runner.calls.length, 0);
});

test('cliente que desconecta cancela a busca (abortEmitter recebe aborted)', async () => {
  const { EventEmitter } = require('events');
  const { ArticlesController } = require('../controllers/articlesController');

  let recebido = null;
  const service = {
    searchMulti: ({ abortEmitter }) => new Promise((resolve, reject) => {
      recebido = abortEmitter;
      abortEmitter.once('aborted', () => {
        const err = new Error('Cliente abortou a requisição.');
        err.statusCode = 499;
        reject(err);
      });
    }),
  };
  const controller = new ArticlesController({ articleSearchService: service });

  const req = { headers: {}, body: { seeds: [{ type: 'doi', value: '10.1000/abc' }] } };
  const res = new EventEmitter();
  res.writableFinished = false;
  res.headersSent = false;
  res.status = () => res;
  res.json = () => res;

  const pending = controller.searchMulti(req, res);
  res.emit('close');
  await pending;

  assert.ok(recebido, 'o serviço precisa receber um abortEmitter');
  assert.equal(recebido.listenerCount('aborted'), 0, 'o listener de abort deve ter disparado');
});

test('parseProgressLine traduz o progresso por seed', () => {
  assert.deepEqual(parseProgressLine('[SEED START] 2/5 doi=10.1000/abc'), {
    stage: 'seed_start', seed: 2, total: 5, message: 'Seed 2/5: searching…',
  });

  const done = parseProgressLine('[SEED DONE] 2/5 status=ok citations=13 references=16');
  assert.equal(done.message, 'Seed 2/5: 13 citations · 16 references');

  assert.equal(
    parseProgressLine('[SEED DONE] 3/5 status=not_found citations=0 references=0').message,
    'Seed 3/5: not found',
  );
  assert.equal(
    parseProgressLine('[SEED DONE] 4/5 status=duplicate citations=0 references=0').message,
    'Seed 4/5: duplicate',
  );
});

test('parseProgressLine mantém a contagem final da busca de uma seed', () => {
  const progress = parseProgressLine('[SOURCE COUNTS] Final forward: citations=3, references=4');
  assert.equal(progress.message, '3 citations · 4 references');
  assert.equal(parseProgressLine('[CACHE MISS]'), null);
});
