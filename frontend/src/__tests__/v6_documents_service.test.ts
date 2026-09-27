import { test } from 'node:test';
import assert from 'node:assert/strict';
import { documentsPaths } from '../api/v6/documents.service';

test('documentsPaths.list formats correctly', () => {
  const result = documentsPaths.list('47');
  assert.ok(result.startsWith('/cases/47/documents'));
});
