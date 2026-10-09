const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..', 'runtime/windows-x64');
const python = path.join(root, 'python');
try {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'runtime-manifest.json'), 'utf8'));
  if (manifest.schema !== 'qianxun-windows-runtime-v1' || manifest.architecture !== 'win32/x64') throw Error('运行环境声明无效');
  for (const name of ['python.exe', 'python312.dll', 'Lib/site-packages/playwright/driver/node.exe']) {
    const file = fs.readFileSync(path.join(python, name));
    if (file.subarray(0, 2).toString() !== 'MZ') throw Error(`缺少有效Windows程序：${name}`);
    const offset = file.readUInt32LE(0x3c);
    if (file.toString('ascii', offset, offset + 4) !== 'PE\0\0' || file.readUInt16LE(offset + 4) !== 0x8664) throw Error(`不是x64程序：${name}`);
  }
  const pth = fs.readFileSync(path.join(python, 'python312._pth'), 'utf8');
  if (!pth.split(/\r?\n/).includes('../../../backend')) throw Error('嵌入式Python缺少后端模块搜索目录');
  for (const entry of manifest.files) {
    const file = path.resolve(python, entry.path);
    if (!file.startsWith(python + path.sep)) throw Error('运行环境文件越界');
    if (crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') !== entry.sha256) throw Error(`运行环境文件损坏：${entry.path}`);
  }
  console.log(`Windows runtime files verified (${manifest.files.length}); Windows real-device execution remains pending.`);
} catch (error) {
  console.error(`Windows安装包未生成：${error.message}。请先准备完整运行环境。`);
  process.exitCode = 1;
}
