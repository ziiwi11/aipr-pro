const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const vault = require('./credential-vault.cjs');
let encryption = null;
const { summarizeUsage } = require('./jev-usage.cjs');
function root() { return process.env.JEV_CONFIG_DIR || path.join(os.homedir(), '.config', 'jev-integration'); }
function status(dir = root()) {
  try {
    const config = JSON.parse(fs.readFileSync(path.join(dir, 'aipr-pro.json'), 'utf8'));
    const enabled = process.env.JEV_INTEGRATION !== '0' && fs.readFileSync(path.join(dir, 'enabled-apps'), 'utf8').split(/\r?\n/).includes('aipr-pro');
    return { usage: summarizeUsage(dir), enabled, configured: Boolean(config.api_key || config.credential_storage === "os-encrypted" && fs.existsSync(path.join(dir,"aipr-pro.credential"))), credentialProtection: config.credential_storage === "os-encrypted" ? (process.platform === "darwin" ? "系统加密（macOS 钥匙串保护）" : "操作系统加密保护") : config.api_key ? "旧配置文件；待迁移系统加密" : "尚无凭据", model: config.model || 'jev-latest', decisionMode: config.decision_mode === true };
  } catch { return { usage: summarizeUsage(dir), enabled: false, configured: false, decisionMode: false }; }
}
function save(payload, dir = root()) {
  let previous = {};
  try { previous = JSON.parse(fs.readFileSync(path.join(dir, 'aipr-pro.json'), 'utf8')); } catch {}
  const apiKey = String(payload?.apiKey || previous.api_key || (previous.credential_storage === 'os-encrypted' ? vault.readCredential(dir,encryption) : '')).trim();
  if (!apiKey || /[\r\n]/.test(apiKey)) throw new Error('请输入有效的 Jev API Key');
  const model = String(payload?.model || previous.model || 'jev-latest').trim();
  if (!/^jev-(?:latest|preview|[0-9]+\.[0-9]+\.[0-9]+)$/.test(model)) throw new Error('请选择 Jev 模型或填写有效版本，例如 jev-1.13.0');
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const config = { ...previous, api_key: apiKey, backend: 'cloud', model, decision_mode: true };
  function write(name, text) {
    const file = path.join(dir, name);
    fs.writeFileSync(`${file}.tmp`, text, { mode: 0o600 });
    fs.chmodSync(`${file}.tmp`, 0o600);
    fs.renameSync(`${file}.tmp`, file);
  }
  let apps = [];
  try { apps = fs.readFileSync(path.join(dir, 'enabled-apps'), 'utf8').split(/\r?\n/).filter(Boolean); } catch {}
  if (encryption) {
    vault.writeCredential(dir,apiKey,encryption);
    delete config.api_key;
    config.credential_storage = 'os-encrypted';
  }
  write('aipr-pro.json', JSON.stringify(config, null, 2));
  write('enabled-apps', [...new Set([...apps, 'aipr-pro'])].join('\n') + '\n');
  return status(dir); // Never return credentials to the renderer.
}
function configureEncryption(provider) { encryption=provider; }
function getApiKey(dir=root()) {
 let config;try {config=JSON.parse(fs.readFileSync(path.join(dir,'aipr-pro.json'),'utf8'));}catch{return '';}
 return config.credential_storage==='os-encrypted' ? vault.readCredential(dir,encryption) : String(config.api_key||'');
}
function migrate(dir=root()) {
 let config;try {config=JSON.parse(fs.readFileSync(path.join(dir,'aipr-pro.json'),'utf8'));}catch{return false;}
 if(!config.api_key) return false;
 if (!vault.available(encryption)) return false;
 save({apiKey:config.api_key,model:config.model},dir);return true;
}
module.exports = { status, save, configureEncryption, getApiKey, migrate };
