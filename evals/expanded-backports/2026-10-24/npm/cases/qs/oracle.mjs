import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);

const qs = require('/work/repo/lib/index.js');

test('test_security', () => {
  const result = qs.parse('entry[__proto__][seam_probe]=local&entry[visible]=ok', {
    allowPrototypes: true,
  });
  assert.equal(Object.getPrototypeOf(result.entry), Object.prototype,
    'QS_LOCAL_PROTOTYPE_PRESERVED');
  assert.equal(result.entry.seam_probe, undefined, 'QS_LOCAL_PROTOTYPE_PRESERVED');
  assert.equal(result.entry.visible, 'ok');
});

test('test_nested_properties', () => {
  assert.deepEqual(qs.parse('entry[name]=demo&entry[count]=2'), {
    entry: { name: 'demo', count: '2' },
  });
});

test('test_repeated_array_values', () => {
  assert.deepEqual(qs.parse('items[]=first&items[]=second'), {
    items: ['first', 'second'],
  });
});
