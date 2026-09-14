import test from 'node:test';
import assert from 'node:assert/strict';
import { requirementsPaths } from '../api/v6/requirements.service';

test('V6 Requirements Service Paths', async (t) => {
  await t.test('list path should build correctly', () => {
    const path = requirementsPaths.list('123');
    assert.equal(path, '/cases/123/requirements');
  });

  await t.test('detail path should build correctly', () => {
    const path = requirementsPaths.detail('123', 45);
    assert.equal(path, '/cases/123/requirements/45');
  });
});
