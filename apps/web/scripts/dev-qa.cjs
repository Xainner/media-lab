// Local UI review: disposable fixture API (5375) + Vite dev server (5374) proxying /v1 to it.
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.join(__dirname, '..');
const api = spawn(process.execPath, [path.join(__dirname, 'qa-api.cjs')], { stdio: 'inherit' });
const vite = spawn(process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'), '--port', '5374', '--strictPort'], { cwd: root, stdio: 'inherit', env: { ...process.env, RVL_API_URL: 'http://127.0.0.1:5375' } });
const stop = () => { api.kill(); vite.kill(); process.exit(0) };
process.on('SIGINT', stop); process.on('SIGTERM', stop);
vite.on('exit', stop); api.on('exit', stop);
