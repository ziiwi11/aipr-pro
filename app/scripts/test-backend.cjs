const {spawnSync} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const python = process.platform === 'win32'
  ? path.join(root, 'runtime/windows-x64/python/python.exe')
  : path.join(root, 'runtime/macos-arm64/python/bin/python3');
const result = spawnSync(python, [path.join(__dirname, 'test-backend.py')], {cwd: root, stdio:'inherit', shell:false});
if (result.error) {console.error('内置Python测试无法启动：' + result.error.message); process.exitCode = 1;}
else process.exitCode = result.status === null ? 1 : result.status;
