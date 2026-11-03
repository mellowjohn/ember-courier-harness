"""Resize evidence must be complete, immutable and included in quality decisions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from ember_harness import gameplay, polish_runtime, task_quality
from ember_harness.recovery import atomic_json
from quality_fixture import aspect_captures
import test_task_quality as quality_fixture

ROOT = Path(__file__).resolve().parents[1]


class ViewportEvidenceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.source = self.area/'input.json'
        atomic_json(self.source, dict(aspect_ratios=polish_runtime.ASPECT_RATIOS, review_sheets=True))
        self.output = self.area/'output'; self.output.mkdir()
        rows = []
        for name in ('desktop', 'mobile'):
            for suffix in ('', '-before'):
                Image.new('RGB', (40, 30)).save(self.output/(name+suffix+'.png'))
            rows.append(dict(name=name, screenshot=name+'.png', sha256=polish_runtime.file_digest(self.output/(name+'.png')),
                before_sha256=polish_runtime.file_digest(self.output/(name+'-before.png'))))
        self.report = dict(complete=True, input_sha256=polish_runtime.file_digest(self.source), viewports=rows)
        aspect_captures(dict(aspect_ratios=polish_runtime.ASPECT_RATIOS, review_sheets=True), self.output, self.report)
        self.save()

    def save(self):
        atomic_json(self.output/'report.json', self.report)

    def test_every_ratio_is_verified_and_packed_without_extra_model_images(self):
        self.assertEqual(polish_runtime.verified_report(self.source, self.output), self.report)
        images = polish_runtime.review_images(self.output)
        self.assertEqual(len(images), 2)
        names = [n for row in self.report['viewports'] for n in row['review_sources']]
        self.assertTrue(all(row['screenshot'] in names for row in self.report['aspect_ratios']))

    def test_retained_legacy_report_does_not_require_new_captures(self):
        atomic_json(self.source, dict(review_sheets=True))
        self.report.pop('aspect_ratios')
        self.report['input_sha256'] = polish_runtime.file_digest(self.source)
        from quality_fixture import review_sheets
        review_sheets(self.output, self.report['viewports'])
        self.save()
        self.assertEqual(polish_runtime.verified_report(self.source, self.output), self.report)

    def test_missing_duplicate_reordered_and_malformed_observations_rejected(self):
        for mutation in ('missing', 'duplicate', 'reordered', 'layout'):
            original = deepcopy(self.report)
            if mutation == 'missing': self.report['aspect_ratios'].pop()
            if mutation == 'duplicate': self.report['aspect_ratios'][-1] = deepcopy(self.report['aspect_ratios'][0])
            if mutation == 'reordered': self.report['aspect_ratios'].reverse()
            if mutation == 'layout': self.report['aspect_ratios'][0]['layout']['document_preserved'] = 'yes'
            self.save()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                polish_runtime.verified_report(self.source, self.output)
            self.report = original

    def test_changed_image_and_sheet_source_omission_are_rejected(self):
        target = self.output/self.report['aspect_ratios'][0]['screenshot']
        original = target.read_bytes(); target.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Aspect-ratio screenshot'):
            polish_runtime.verified_report(self.source, self.output)
        target.write_bytes(original)
        self.report['viewports'][0]['review_sources'].pop(); self.save()
        with self.assertRaisesRegex(ValueError, 'incomplete evidence'):
            polish_runtime.verified_report(self.source, self.output)

    def test_enthusiastic_verdict_cannot_skip_ratios_or_override_clipped_controls(self):
        fixture = quality_fixture.TaskQualityTests(); fixture.setUp()
        observed = fixture.observed
        observed['aspect_ratios'] = deepcopy(self.report['aspect_ratios'])
        verdict = fixture.verdict
        self.assertTrue(any('every supplied aspect ratio' in b for b in task_quality.review(fixture.quality, verdict, fixture.files, observed)['blockers']))
        row = next(r for r in verdict['criteria'] if r['id']=='game-viewport-fit')
        row['evidence'] += [dict(kind='capture', ref=r['screenshot'], detail='SYNTHETIC resize review') for r in observed['aspect_ratios']]
        self.assertEqual(task_quality.review(fixture.quality, verdict, fixture.files, observed)['blockers'], [])
        observed['aspect_ratios'][-1]['layout']['clipped_controls'] = ['Throw']
        self.assertTrue(any('controls outside viewport' in b for b in task_quality.review(fixture.quality, verdict, fixture.files, observed)['blockers']))
        self.assertEqual(gameplay.capture_outcome(observed), 'failed')
