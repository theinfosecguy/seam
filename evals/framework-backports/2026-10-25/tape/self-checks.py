"""Validate the frozen research conclusions, without executing target code."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
data = json.loads((root / 'outcomes.json').read_text())
expected = {
    'qs': [(81, 215), (82, 223), (80, 211), (81, 219)],
    'fast-uri': [(7, 56), (8, 105), (7, 56), (8, 105)],
}
for package, counts in expected.items():
    revisions = data['real_suite_prerequisites'][package]
    for revision, pair in zip(
        ['upstream_parent', 'upstream_fix', 'target_baseline', 'maintainer_backport'],
        counts,
        strict=True,
    ):
        row = revisions[revision]
        assert (row['scope_count'], row['assertion_count']) == pair
        assert row['exit_code'] == 0
        assert row['closed_scope_count'] == row['scope_count']
        assert row['stream_end_count'] == 1
        assert row['failed_assertions'] == row['skipped_or_todo_events'] == 0
        assert row['duplicate_scope_identities'] == []
    target = revisions['target_baseline']
    assert target['repeat_identities_match']
    assert target['repeat_assertion_results_match']
s = data['synthetic_observations']
assert s['late-async']['stream_end_count'] == 1
assert s['late-async']['failed_assertions'] == 0
assert s['late-async']['exit_code'] == 1
assert s['plan-short']['plan_mismatch_events'] == 1
assert s['no-end']['stream_end_count'] == 0
assert s['premature-exit']['stream_end_count'] == 0
assert s['skip']['skipped_or_todo_events'] == 1
assert s['opts-skip']['skipped_or_todo_events'] == 1
assert s['custom-harness']['exit_code'] == 0
assert s['custom-harness']['scope_count'] == 1
assert s['custom-harness']['failed_assertions'] == 0
assert s['secondary-tape']['malformed_output_lines'] > 0
assert s['empty-scope']['scope_count'] == 1
assert s['empty-scope']['assertion_count'] == 0
assert s['only']['exit_code'] == 1
assert s['only']['scope_count'] == 0
r = data['reporter_observations']
assert r['captured-normal.tap']['tap_junit']['duplicate_identities']
assert r['captured-normal.tap']['tapjs_corrected_import']['case_count'] == 0
assert r['bailout.tap']['strict_parser']['bailout']
assert r['no-plan.tap']['strict_parser']['ok'] is False
pins = json.loads((root / 'pins.json').read_text())
assert hashlib.sha256((root / 'package-lock.json').read_bytes()).hexdigest() == pins['package_lock_sha256']
for path in root.rglob('*'):
    if path.is_file():
        text = path.read_text()
        assert chr(47) + 'home' + chr(47) not in text, path.name
print('Frozen outcome, identity repeat, lifecycle, reporting and publication checks passed.')
