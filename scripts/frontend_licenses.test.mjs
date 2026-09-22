import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { collect, prepare } from './frontend_licenses.mjs';

function fixture(t) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'decmapf-notices-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const packageDir = path.join(root, 'frontend/node_modules/example');
  mkdirSync(packageDir, { recursive: true });
  mkdirSync(path.join(root, 'docs/licenses'), { recursive: true });
  writeFileSync(path.join(root, 'LICENSE'), 'Project copyright and terms');
  writeFileSync(path.join(root, 'docs/licenses/frontend-overrides.json'), '{}');
  writeFileSync(path.join(root, 'frontend/package-lock.json'), JSON.stringify({ packages: {
    '': { name: 'fixture' }, 'node_modules/example': { version: '1.0.0', resolved: 'https://example.org/example.tgz', integrity: 'sha512-fixture' }
  } }));
  writeFileSync(path.join(packageDir, 'package.json'), JSON.stringify({ name: 'example', version: '1.0.0', license: 'MIT' }));
  writeFileSync(path.join(packageDir, 'LICENSE'), 'Upstream copyright and permission');
  writeFileSync(path.join(packageDir, 'NOTICE'), 'Additional attribution');
  return { root, packageDir };
}

test('copies complete license and NOTICE alongside the browser bundle', t => {
  const { root } = fixture(t);
  prepare(root, true);
  prepare(root);
  const text = readFileSync(path.join(root, 'frontend/public/THIRD_PARTY_NOTICES.txt'), 'utf8');
  assert.match(text, /Upstream copyright and permission/);
  assert.match(text, /Additional attribution/);
});

test('rejects absent copyright notice despite a valid SPDX label', t => {
  const { root, packageDir } = fixture(t);
  rmSync(path.join(packageDir, 'LICENSE'));
  rmSync(path.join(packageDir, 'NOTICE'));
  assert.throws(() => collect(root), /Missing license text/);
});

test('rejects installed dependency drift before producing output', t => {
  const { root, packageDir } = fixture(t);
  writeFileSync(path.join(packageDir, 'package.json'), JSON.stringify({ name: 'example', version: '2.0.0', license: 'MIT' }));
  assert.throws(() => collect(root), /differs from lock/);
});

test('requires explicit review when upstream terms change', t => {
  const { root, packageDir } = fixture(t);
  prepare(root, true);
  writeFileSync(path.join(packageDir, 'LICENSE'), 'Changed terms');
  assert.throws(() => prepare(root), /Stale notices/);
});
