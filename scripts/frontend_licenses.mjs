/** Preserve notices for the locked runtime closure and Vite's injected runtime helper. */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const digest = (data) => createHash('sha256').update(data).digest('hex');
export function collect(root) {
  const lockBytes = readFileSync(path.join(root, 'frontend/package-lock.json'));
  const lock = JSON.parse(lockBytes);
  const components = [];
  const overrides = JSON.parse(readFileSync(path.join(root, 'docs/licenses/frontend-overrides.json')));
  const blocks = ['DEC-MAPF GUI — license notices', readFileSync(path.join(root, 'LICENSE'), 'utf8'),
    'The following notices cover the locked production dependency closure (including types and optional code) and the Vite runtime helper. Listing a package does not imply every file in that package is included in the minified bundle.'];
  for (const [key, value] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b, 'en'))) {
    if (!key || (value.dev && key !== 'node_modules/vite')) continue;
    if (!key.startsWith('node_modules/') || key.includes('..')) throw new Error(`Unexpected dependency path: ${key}`);
    const dir = path.join(root, 'frontend', key);
    const meta = JSON.parse(readFileSync(path.join(dir, 'package.json')));
    if (meta.version !== value.version) throw new Error(`Installed version differs from lock: ${key}`);
    if (!meta.license || !['MIT', 'ISC', 'BSD-3-Clause'].includes(meta.license)) {
      throw new Error(`Review license terms before updating: ${key}: ${meta.license}`);
    }
    const names = readdirSync(dir, { withFileTypes: true }).filter(e => e.isFile() && /^(licen[cs]e|copying|notice)([.-]|$)/i.test(e.name)).map(e => e.name).sort();
    const texts = names.map(name => ({ name, text: readFileSync(path.join(dir, name), 'utf8') }));
    if (!texts.length) {
      const override = overrides[meta.name];
      if (!override || override.version !== meta.version) throw new Error(`Missing license text: ${key}`);
      const text = readFileSync(path.join(root, 'docs/licenses', override.file), 'utf8');
      if (digest(text) !== override.sha256) throw new Error(`Changed upstream notice: ${key}`);
      texts.push({ name: override.file, text, source: override.url });
    }
    if (texts.some(t => !t.text.trim())) throw new Error(`Empty license text: ${key}`);
    components.push({ name: meta.name, version: meta.version, license: meta.license,
      package_path: key, source: value.resolved, integrity: value.integrity,
      notices: texts.map(t => ({ file: t.name, ...(t.source ? { source: t.source } : {}), sha256: digest(t.text) })) });
    blocks.push(`\n${'='.repeat(72)}\n${meta.name} ${meta.version} (${meta.license})\n${value.resolved}`);
    for (const t of texts) blocks.push(`--- ${t.name} ---\n${t.text}`);
  }
  const notices = blocks.join('\n\n') + '\n';
  return { inventory: JSON.stringify({ scope: 'GUI runtime closure plus Vite helper; full texts govern',
    lock_sha256: digest(lockBytes), notices_sha256: digest(notices), components }, null, 2) + '\n', notices };
}

export function prepare(root, update = false) {
  const result = collect(root);
  const outputs = [['frontend.json', 'license-inventory.json', result.inventory], ['frontend.txt', 'THIRD_PARTY_NOTICES.txt', result.notices]];
  for (const [name, publicName, data] of outputs) {
    const approved = path.join(root, 'docs/licenses', name);
    if (update) { mkdirSync(path.dirname(approved), { recursive: true }); writeFileSync(approved, data); }
    if (!existsSync(approved) || readFileSync(approved, 'utf8') !== data) {
      throw new Error(`Stale notices: ${name}. Review dependency terms, then run node scripts/frontend_licenses.mjs --write.`);
    }
    const target = path.join(root, 'frontend/public', publicName);
    mkdirSync(path.dirname(target), { recursive: true }); writeFileSync(target, data);
  }
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  prepare(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'), process.argv.includes('--write'));
  console.log('GUI license notices verified and copied to the build inputs.');
}
