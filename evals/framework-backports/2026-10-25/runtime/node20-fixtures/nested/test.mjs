import {test, describe} from 'node:test';
import assert from 'node:assert/strict';
describe('outer', () => { test('leaf', () => {}); });
