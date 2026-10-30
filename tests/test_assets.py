"""Asset permissions, human decisions, immutable selection and stale-byte rejection."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jsonschema import ValidationError

from ember_harness import Harness, content_hash, canonical
from ember_harness.assets import Assets, parse_manifest
from ember_harness.contract_lock import verify
from ember_harness.scope import propose
from examples.asset_demo import fixture_images


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'project/scope-output'
        self.candidates = fixture_images(self.output / 'candidates')
        (self.output / 'assets').mkdir()
        self.manifest = self.output / 'manifest.json'
        self.write_manifest()
        self.h = Harness(self.root / 'state')
        self.assets = Assets(self.h)
        self.scope = propose('ct-asset-scope-0001', 'planner', 'Choose a local original ember', self.root / 'project', asset_workflow=True)
        self.scope['approval_mode'] = 'approve_all'
        self.approve(self.scope)
        self.child = self.assets.proposal(self.scope['id'], self.manifest, 'ct-assets-0001', 'artist')
        self.approve(self.child, self.scope['id'])
        self.cid = self.child['id']
        self.assertTrue(self.h.verify_inputs(self.cid))
        self.dest = self.output / 'assets/player.png'

    def write_manifest(self):
        self.manifest.write_bytes(canonical(dict(topic='Player ember', candidates=self.candidates)))

    def approve(self, c, parent=None):
        self.h.save_draft(c)
        return self.h.approve(c['id'], 1, approver='johnathan', quote='Simulated fixture approval',
                              expected_hash=content_hash(c), parent_id=parent)

    def review(self):
        return self.assets.review(self.cid)['review_ref']

    def select(self, ref):
        result = self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.assertEqual(result['decision'], 'needs_approval')
        self.h.approve_action(result['approval_action'], approver='johnathan', quote='Simulated fixture choice')
        return self.assets.select(self.cid, ref, self.candidates[0]['slug'])

    def ingest(self):
        ref = self.review()
        self.select(ref)
        self.assertEqual(self.assets.ingest(self.cid, ref, self.dest)['status'], 'ingested')
        return ref

    def test_selection_and_acceptance_never_auto_resolve(self):
        ref = self.ingest()
        self.assertEqual(self.assets.status(self.cid, ref, self.dest)['status'], 'awaiting_acceptance')
        pending = self.assets.accept(self.cid, ref, self.dest)
        self.assertEqual(pending['decision'], 'needs_approval')
        self.h.approve_action(pending['approval_action'], approver='johnathan', quote='Simulated fixture acceptance')
        self.assertEqual(self.assets.accept(self.cid, ref, self.dest)['status'], 'accepted')
        self.assertEqual(self.assets.accept(self.cid, ref, self.dest)['decision'], 'needs_approval')
        self.assertTrue(verify(self.h.root)['ok'])

    def test_unselected_and_outside_writes_are_rejected(self):
        ref = self.review()
        with self.assertRaisesRegex(ValueError, 'selection'):
            self.assets.ingest(self.cid, ref, self.dest)
        self.select(ref)
        outside = self.root / 'outside.png'
        with self.assertRaises(ValueError):
            self.assets.ingest(self.cid, ref, outside)
        self.assertFalse(outside.exists())

    def test_create_only_even_if_existing_bytes_are_identical(self):
        ref = self.ingest()
        original = self.dest.read_bytes()
        with self.assertRaises(FileExistsError):
            self.assets.ingest(self.cid, ref, self.dest)
        self.assertEqual(self.dest.read_bytes(), original)
        self.dest.write_bytes(b'keep existing different bytes')
        with self.assertRaises(ValueError):
            self.assets.ingest(self.cid, ref, self.dest)
        self.assertEqual(self.dest.read_bytes(), b'keep existing different bytes')

    def test_changed_source_and_manifest_cannot_be_selected_or_ingested(self):
        ref = self.review()
        source = Path(self.candidates[0]['path'])
        original = source.read_bytes()
        source.write_bytes(b'changed')
        pending = self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.h.approve_action(pending['approval_action'], approver='johnathan', quote='Fixture stale choice')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.assertFalse(any(e['kind'] == 'concept_selection' for e in self.h._entries()))
        source.write_bytes(original)
        self.select(ref)
        self.manifest.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.assets.ingest(self.cid, ref, self.dest)
        self.assertFalse(self.dest.exists())

    def test_changed_destination_cannot_be_accepted(self):
        ref = self.ingest()
        pending = self.assets.accept(self.cid, ref, self.dest)
        self.h.approve_action(pending['approval_action'], approver='johnathan', quote='Fixture choice')
        self.dest.write_bytes(b'changed')
        with self.assertRaises((ValueError, KeyError)):
            self.assets.accept(self.cid, ref, self.dest)
        self.assertEqual(self.assets.status(self.cid, ref, self.dest)['status'], 'incomplete')
        self.assertFalse(any(e['kind'] == 'asset_acceptance' for e in self.h._entries()))

    def test_tampered_review_and_wrong_choice_rejected(self):
        ref = self.review()
        with self.assertRaisesRegex(ValueError, 'not a reviewed'):
            self.assets.select(self.cid, ref, 'nonexistent')
        path = self.h.root / 'concepts' / ref / 'review.json'
        path.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.assertFalse(verify(self.h.root)['ok'])

    def test_different_contract_cannot_reuse_review(self):
        ref = self.review()
        other = self.assets.proposal(self.scope['id'], self.manifest, 'ct-other-assets-0001', 'other')
        self.approve(other, self.scope['id'])
        self.assertTrue(self.h.verify_inputs(other['id']))
        with self.assertRaisesRegex(ValueError, 'different contract'):
            self.assets.select(other['id'], ref, self.candidates[0]['slug'])

    def test_duplicate_selection_and_wrong_choice_approval_reject(self):
        ref = self.review()
        pending = self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.h.approve_action(pending['approval_action'], approver='johnathan', quote='Fixture')
        wrong = self.assets.select(self.cid, ref, self.candidates[1]['slug'])
        self.assertEqual(wrong['decision'], 'needs_approval')
        self.assets.select(self.cid, ref, self.candidates[0]['slug'])
        self.assertEqual(self.assets.select(self.cid, ref, self.candidates[0]['slug'])['decision'], 'needs_approval')
        pending = self.assets.select(self.cid, ref, self.candidates[1]['slug'])
        self.h.approve_action(pending['approval_action'], approver='johnathan', quote='Fixture')
        with self.assertRaisesRegex(ValueError, 'selection already recorded'):
            self.assets.select(self.cid, ref, self.candidates[1]['slug'])

    def test_revoked_parent_blocks_ingest(self):
        ref = self.review()
        self.select(ref)
        self.h.revoke(self.scope['id'], approver='johnathan', reason='Fixture revocation')
        with self.assertRaises(ValueError):
            self.assets.ingest(self.cid, ref, self.dest)
        self.assertFalse(self.dest.exists())

    def test_audit_failure_never_claims_ingest_or_acceptance(self):
        ref = self.review()
        self.select(ref)
        original = self.h._append
        def broken(kind, **kwargs):
            if kind == 'asset_ingest':
                raise OSError('fixture audit unavailable')
            return original(kind, **kwargs)
        with patch.object(self.h, '_append', side_effect=broken), self.assertRaises(OSError):
            self.assets.ingest(self.cid, ref, self.dest)
        self.assertTrue(self.dest.exists())  # Interrupted writes remain unclaimed, never silently overwritten.
        with self.assertRaisesRegex(ValueError, 'audited ingest'):
            self.assets.accept(self.cid, ref, self.dest)
        self.assertFalse(any(e['kind'] == 'asset_ingest' for e in self.h._entries()))

    def test_invalid_manifest_rejects_duplicate_paths_and_commands(self):
        manifest = dict(topic='ember', candidates=deepcopy(self.candidates))
        manifest['candidates'][1]['path'] = manifest['candidates'][0]['path']
        with self.assertRaisesRegex(ValueError, 'unique'):
            parse_manifest(canonical(manifest))
        manifest = dict(topic='ember', candidates=self.candidates, command='publish')
        with self.assertRaises(ValidationError):
            parse_manifest(canonical(manifest))

    def technical_contract(self):
        self.write_manifest()
        c = self.assets.proposal(self.scope['id'], self.manifest, 'ct-technical-0001', 'technical-reviewer')
        self.approve(c, self.scope['id'])
        self.assertTrue(self.h.verify_inputs(c['id']))
        return c['id']

    def test_corrupt_png_dimensions_and_required_alpha_fail(self):
        source = Path(self.candidates[0]['path'])
        source.write_bytes(b'not a png')
        self.candidates[0]['sha256'] = sha256(source.read_bytes()).hexdigest()
        cid = self.technical_contract()
        with self.assertRaises(OSError):
            self.assets.review(cid)
        self.assertFalse(any(e['kind'] == 'concept_review' for e in self.h._entries()))

    def test_declared_dimensions_are_enforced(self):
        self.candidates[0]['target'] = [32, 32]
        cid = self.technical_contract()
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            self.assets.review(cid)

    def test_required_alpha_is_enforced(self):
        from PIL import Image
        source = Path(self.candidates[0]['path'])
        with Image.open(source) as image:
            rgb = image.convert('RGB')
        rgb.save(source)
        self.candidates[0]['sha256'] = sha256(source.read_bytes()).hexdigest()
        cid = self.technical_contract()
        with self.assertRaisesRegex(ValueError, 'alpha'):
            self.assets.review(cid)

    def test_no_arbitrary_minimum_dimensions_without_target(self):
        from PIL import Image
        source = Path(self.candidates[0]['path'])
        Image.new('RGBA', (1, 1), (255, 0, 0, 255)).save(source)
        self.candidates[0].pop('target')
        self.candidates[0]['sha256'] = sha256(source.read_bytes()).hexdigest()
        cid = self.technical_contract()
        result = self.assets.review(cid)
        self.assertEqual(result['review']['candidates'][0]['dimensions'], [1, 1])

    def test_snapshot_audit_failure_creates_no_selectable_review(self):
        original = self.h._append
        def broken(kind, **kwargs):
            if kind == 'concept_review':
                raise OSError('fixture review audit failure')
            return original(kind, **kwargs)
        with patch.object(self.h, '_append', side_effect=broken), self.assertRaises(OSError):
            self.review()
        ref = next((self.h.root / 'concepts').iterdir()).name
        with self.assertRaisesRegex(ValueError, 'audited concept review'):
            self.assets.select(self.cid, ref, self.candidates[0]['slug'])

    def test_extra_required_evidence_cannot_be_bypassed_by_acceptance(self):
        c = self.assets.proposal(self.scope['id'], self.manifest, 'ct-extra-0001', 'extra')
        c['required_evidence']['asset_copy'].append({'kind': 'checklist', 'params': {'items': ['QA checked']}})
        self.approve(c, self.scope['id'])
        self.cid = c['id']
        self.assertTrue(self.h.verify_inputs(self.cid))
        ref = self.review()
        self.select(ref)
        self.assertEqual(self.assets.ingest(self.cid, ref, self.dest)['status'], 'incomplete')
        with self.assertRaisesRegex(ValueError, 'complete copy evidence'):
            self.assets.accept(self.cid, ref, self.dest)

    def test_real_cli_lifecycle(self):
        from examples.asset_demo import main
        result = main()
        self.assertTrue(result['report'].is_file())
        self.assertGreaterEqual(len(result['scenarios']), 12)
