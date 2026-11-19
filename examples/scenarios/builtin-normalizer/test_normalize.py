"""Eight frozen methods, nine recorded input observations, no repair-owned tests."""
import json
from pathlib import Path
import unittest

from normalize import normalize_spaces


CASES = {row['case_id']: row for row in json.loads(
    Path(__file__).with_name('cases.json').read_text(encoding='utf-8'))['cases']}
OBSERVATIONS = []


class NormalizeSpacesTests(unittest.TestCase):
    def _exercise(self, case_id):
        for index, value in enumerate(CASES[case_id]['inputs']):
            with self.subTest(case_id=case_id, input_index=index):
                row = dict(index=index, input=value['input'], expected=value['expected'],
                           observed=None, observed_present=False, status='error', error='')
                OBSERVATIONS.append({'case_id': case_id, 'input': row})
                try:
                    observed = normalize_spaces(value['input'])
                    # Preserve the actual function value before the assertion.
                    row.update(observed=observed, observed_present=True)
                    if not isinstance(observed, str):
                        row.update(observed=repr(observed), error='non-string return value')
                        raise TypeError('normalize_spaces must return str')
                    row['status'] = 'pass' if observed == value['expected'] else 'fail'
                except Exception as exc:
                    row['error'] = f'{type(exc).__name__}: {exc}'
                    raise
                self.assertEqual(observed, value['expected'])

    def test_repeated_spaces(self):
        self._exercise('repeated-spaces')

    def test_repeated_tabs(self):
        self._exercise('repeated-tabs')

    def test_embedded_newline(self):
        self._exercise('embedded-newline')

    def test_mixed_whitespace(self):
        self._exercise('mixed-whitespace')

    def test_edge_whitespace(self):
        self._exercise('edge-whitespace')

    def test_already_normalized(self):
        self._exercise('already-normalized')

    def test_unicode_punctuation(self):
        self._exercise('unicode-punctuation')

    def test_empty_blank(self):
        self._exercise('empty-blank')
