"""Real private Git commits and gates, with synthetic owner/browser observations."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import shutil
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import test_chat_build as builds
import test_gameplay as checks
import test_task_run as tasks
from ember_harness import chat_build, gameplay, git_task, mechanic_recipes, mechanic_workflow, project_plan
from ember_harness.contract_lock import git
from ember_harness.core import subset, validate
from ember_harness.local_ui import server
from ember_harness.recovery import atomic_json, read_json


class GitBrowserTaskTests(unittest.TestCase):
    def setUp(self):
        checkout = next((path for path in (builds.ROOT, *builds.ROOT.parents) if (path / '.git').is_dir()), builds.ROOT)
        scratch = checkout / '.harness'; scratch.mkdir(parents=True, exist_ok=True)
        real_temp = builds.tempfile.TemporaryDirectory
        def short_temp(*args, **kwargs):
            return real_temp(*args, **{**kwargs, 'dir': scratch, 'prefix': 'g'})
        self.fixture = tasks.TaskRunTests()
        with patch('test_chat_build.tempfile.TemporaryDirectory', side_effect=short_temp):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.candidate = {**builds.PROJECT, 'app.js': builds.PROJECT['app.js'].replace(' + 1;', ' + 2;')}
        self.plan = deepcopy(checks.PLAN)
        self.plan['scenarios'][0]['steps'][-1]['value'] = 2
        gameplay.save(self.folder, self.plan, 1)
        self.inspect_calls = []
        self.baseline_fails, self.candidate_passes = True, True

    def prepare(self, **kwargs):
        return git_task.prepare(self.root, self.folder, candidate_files=self.candidate, **kwargs)['id']

    def approve(self, run):
        return git_task.respond(self.root, self.folder, run, 'approve', 'SYNTHETIC reviewed exact local Git task')

    def inspect(self, runtime, source, output, **kwargs):
        self.inspect_calls.append(source.parent.name)
        observed = self.fixture.fixture.browser(runtime, source, output, **kwargs)
        failed = self.baseline_fails if source.parent.name == '0' else not self.candidate_passes
        observed['gameplay'] = checks.result(read_json(source)['gameplay_plan'], failed=failed)
        atomic_json(output / 'report.json', observed)
        return observed

    def run_worker(self, run, inspect=None):
        with patch('ember_harness.polish_runtime.inspect', side_effect=inspect or self.inspect), patch('ember_harness.muse_chat.run') as provider:
            git_task.Worker(self.root, self.folder, run).run()
            provider.assert_not_called()
        return git_task.history(self.root, self.folder)[-1]

    def test_reviewed_exact_repair_clean_builds_and_separate_application(self):
        run = self.prepare()
        work, h, packet, plan = git_task.load(self.folder, run)
        self.assertFalse((work / 'baseline/.git').exists())
        with self.assertRaisesRegex(ValueError, 'Approve exact'):
            git_task.Worker(self.root, self.folder, run).run()
        self.assertNotEqual(packet['body']['contracts'][0]['contract']['agent'], packet['body']['contracts'][1]['contract']['agent'])
        self.approve(run)
        row = self.run_worker(run)
        self.assertEqual(row['status'], 'ready_review', row.get('error'))
        report = row['report']
        self.assertTrue(report['qualified'])
        self.assertEqual(report['before']['gameplay']['outcome'], 'failed')
        self.assertEqual(report['after']['gameplay']['outcome'], 'passed')
        self.assertTrue(report['contract_lock']['ok'])
        self.assertEqual(git(work / 'candidate', 'rev-parse', 'HEAD^').decode().strip(), report['base'])
        for area, build in [('baseline', report['base']), ('verify-before', report['base']), ('candidate', report['head']), ('verify-head', report['head'])]:
            self.assertEqual(git(work / area, 'rev-parse', 'HEAD').decode().strip(), build)
            self.assertFalse(git(work / area, 'status', '--porcelain'))
        message = git(work / 'candidate', 'show', '-s', '--format=%B', 'HEAD').decode()
        self.assertIn('Contract-Id: ' + packet['body']['contracts'][0]['contract']['id'], message)
        self.assertIn('Contract-Version: 1', message)
        before_input, after_input = [read_json(work / 'captures' / str(index) / 'input.json') for index in (0, 1)]
        self.assertEqual(before_input['gameplay_plan'], after_input['gameplay_plan'])
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], plan['application_manifest'])
        self.assertIn('data:text/javascript;base64', git_task.preview(self.folder, run)['html'])
        self.assertTrue(git_task.image(self.folder, run, 'baseline', 'desktop.png').startswith(b'\x89PNG'))
        with self.assertRaises(ValueError):
            git_task.image(self.folder, run, 'candidate', '../input.json')
        ref = git_task.promote(self.root, self.folder, run)['request_ref']
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])
        self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'promoted')
        self.app.respond(ref, 'approve', 'SYNTHETIC final exact game review')
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], plan['candidate_manifest'])
        self.assertTrue(h.audit_verify()['ok'])

    def test_non_reproducing_baseline_stops_before_candidate_and_attempts_do_not_reset(self):
        self.baseline_fails = False
        for index in range(3):
            run = self.prepare(goal='Repair attempt ' + str(index))
            self.approve(run)
            row = self.run_worker(run)
            self.assertEqual(row['status'], 'needs_changes', row.get('error'))
            self.assertIsNone(row['report']['head'])
            self.assertFalse((git_task.run_folder(self.folder, run) / 'candidate').exists())
            with self.assertRaisesRegex(ValueError, 'qualifying'):
                git_task.promote(self.root, self.folder, run)
        with self.assertRaisesRegex(ValueError, 'allowance'):
            self.prepare(goal='Renaming cannot reset the selected task allowance')
        renewed = project_plan.status(self.root, self.folder)
        ref = project_plan.prepare(self.root, self.folder, renewed['approved']['document'], renewed['latest_ref'])['request_ref']
        project_plan.acknowledge(self.root, self.folder, ref, 'SYNTHETIC allowance-preserving renewal')
        self.app.respond(ref, 'approve', 'SYNTHETIC renewed scope does not reset task attempts')
        with self.assertRaisesRegex(ValueError, 'allowance'):
            self.prepare(goal='Scope renewal cannot reset the selected task allowance')
        blocked = git_task.history(self.root, self.folder)[-1]
        with self.assertRaisesRegex(ValueError, 'Review the current blocked task'):
            self.app.git_control(self.folder.name, 'escalate', run_id=run, choice='retry', state_hash='0' * 64)
        requests_before = len(git_task.requests(self.folder))
        with patch('ember_harness.muse_chat.run') as provider:
            self.app.git_control(self.folder.name, 'escalate', run_id=run, choice='retry', state_hash=blocked['attempts']['state_hash'])
            after = git_task.history(self.root, self.folder)[-1]
            self.assertEqual(after['task_identity'], blocked['task_identity'])
            self.assertEqual(after['attempts']['allowance'], 4)
            self.assertEqual(len(after['attempts']['attempts']), 3)
            self.assertEqual(len(git_task.requests(self.folder)), requests_before)
            with self.assertRaisesRegex(ValueError, 'Review the current blocked task'):
                self.app.git_control(self.folder.name, 'escalate', run_id=run, choice='retry', state_hash=blocked['attempts']['state_hash'])
            fourth = self.prepare(goal='Explicit extra allowance still needs exact permissions')
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'awaiting_approval')
            self.assertFalse((git_task.run_folder(self.folder, fourth) / 'baseline/.git').exists())
            self.assertEqual(len(git_task.history(self.root, self.folder)[-1]['attempts']['attempts']), 3)
            provider.assert_not_called()

    def test_stale_pending_scope_cannot_approve_but_can_decline_and_prepare_again(self):
        run = self.prepare()
        work, h, packet, plan = git_task.load(self.folder, run)
        state = project_plan.status(self.root, self.folder)
        ref = project_plan.prepare(self.root, self.folder, state['approved']['document'], state['latest_ref'])['request_ref']
        project_plan.acknowledge(self.root, self.folder, ref, 'SYNTHETIC reviewed scope renewal')
        self.app.respond(ref, 'approve', 'SYNTHETIC renewed parent scope')
        with patch('ember_harness.git_task.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'scope changed'):
                git_task.respond(self.root, self.folder, run, 'approve', 'SYNTHETIC stale approval')
            self.assertEqual(git_task.respond(self.root, self.folder, run, 'decline', 'SYNTHETIC discard stale review')['status'], 'declined')
            self.assertEqual(git_task.respond(self.root, self.folder, run, 'decline', 'SYNTHETIC repeat discard')['status'], 'declined')
            fresh = self.prepare()
            self.assertNotEqual(fresh, run)
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'awaiting_approval')
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['attempts']['attempts'], [])
            launch.assert_not_called()
        self.assertFalse((work / 'baseline/.git').exists())

    def test_audited_preparation_recovers_missing_controls_without_new_authority(self):
        original = git_task.atomic_json
        for boundary in ('run.json', 'state.json'):
            def fail_control(path, value):
                if path.name == boundary:
                    raise OSError('SYNTHETIC preparation control interruption')
                return original(path, value)
            with self.subTest(boundary=boundary), patch('ember_harness.git_task.atomic_json', side_effect=fail_control):
                with self.assertRaisesRegex(OSError, 'control interruption'):
                    self.prepare()
            row = git_task.requests(self.folder)[-1]
            run = row['payload']['body']['git_task']['id']
            work, h, packet, plan = git_task.load(self.folder, run)
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['request_ref'], row['ref'])
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'awaiting_approval')
            with self.assertRaisesRegex(ValueError, 'Approve exact'):
                git_task.Worker(self.root, self.folder, run).run()
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['attempts']['attempts'], [])
            self.assertFalse((work / 'baseline/.git').exists())
            if boundary == 'run.json':
                original(work / 'run.json', dict(request_ref='f' * 64))
                with self.assertRaises((ValueError, OSError)):
                    git_task.load(self.folder, run)
                self.assertEqual(read_json(work / 'run.json'), dict(request_ref='f' * 64))
                (work / 'run.json').unlink()
            original(work / 'run.json', dict(request_ref=row['ref']))
            with patch('ember_harness.git_task.chat_build.harness', return_value=h), patch.object(h, '_entries',
                    return_value=[e for e in h._entries() if not (e['kind'] == 'owner_request' and e['request_ref'] == row['ref'])]):
                with self.assertRaisesRegex(ValueError, 'audited owner request'):
                    git_task.load(self.folder, run)
                self.assertNotIn(run, [saved['id'] for saved in git_task.history(self.root, self.folder)])
            git_task.respond(self.root, self.folder, run, 'decline', 'SYNTHETIC discard recovered control review')
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'declined')

    def test_decision_receipt_recovers_initial_state_without_reapproving(self):
        original = git_task.atomic_json
        for choice, expected in (('approve', 'ready'), ('decline', 'declined')):
            run = self.prepare()
            work, h, packet, plan = git_task.load(self.folder, run)
            def fail_state(path, value):
                if path == work / 'state.json':
                    raise OSError('SYNTHETIC display interruption after owner receipt')
                return original(path, value)
            with self.subTest(choice=choice), patch('ember_harness.git_task.atomic_json', side_effect=fail_state):
                with self.assertRaisesRegex(OSError, 'after owner receipt'):
                    git_task.respond(self.root, self.folder, run, choice, 'SYNTHETIC exact permission decision')
            self.assertEqual(read_json(work / 'state.json')['status'], 'awaiting_approval')
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], expected)
            events = h._entries()
            for _ in range(2):
                self.assertEqual(git_task.respond(self.root, self.folder, run, choice, 'SYNTHETIC replay same decision')['status'], expected)
            self.assertEqual(h._entries(), events)
            with self.assertRaisesRegex(ValueError, 'already decided'):
                git_task.respond(self.root, self.folder, run, 'decline' if choice == 'approve' else 'approve', 'SYNTHETIC conflicting choice')
            self.assertFalse((work / 'baseline/.git').exists())
            self.assertEqual(git_task.history(self.root, self.folder)[-1]['attempts']['attempts'], [])
            if choice == 'approve':
                git_task.stop(self.root, self.folder, run)

    def test_partial_contract_receipt_does_not_infer_an_owner_batch_decision(self):
        run = self.prepare()
        work, h, packet, plan = git_task.load(self.folder, run)
        item = packet['body']['contracts'][0]
        from ember_harness.core import content_hash
        h.approve(item['contract']['id'], 1, approver='johnathan', quote='SYNTHETIC partial owner batch',
            expected_hash=content_hash(item['contract']), parent_id=item['parent_id'])
        self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'awaiting_approval')
        with self.assertRaisesRegex(ValueError, 'Approve exact'):
            git_task.Worker(self.root, self.folder, run).run()
        self.assertFalse((work / 'baseline/.git').exists())
        self.assertEqual(git_task.history(self.root, self.folder)[-1]['attempts']['attempts'], [])
        git_task.respond(self.root, self.folder, run, 'decline', 'SYNTHETIC discard interrupted batch')
        self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'declined')

    def test_candidate_failure_cannot_be_recommended_and_evidence_tampering_refuses(self):
        self.candidate_passes = False
        run = self.prepare(); self.approve(run)
        row = self.run_worker(run)
        self.assertFalse(row['report']['qualified'])
        with self.assertRaises(ValueError):
            git_task.promote(self.root, self.folder, run)
        work = git_task.run_folder(self.folder, run)
        for target in (work / 'verify-before/app.js', work / 'captures/1/output/mobile.png', work / 'candidate/.git/config', work / 'report.json'):
            raw = target.read_bytes()
            target.write_bytes(b'tampered')
            with self.subTest(target=target), self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                git_task.completed_report(self.folder, run)
            target.write_bytes(raw)

    def test_interrupted_verifier_replays_captures_commits_and_one_allocation(self):
        run = self.prepare(); self.approve(run)
        interrupted = False
        def inspect(*args, **kwargs):
            nonlocal interrupted
            if args[1].parent.name == '1' and not interrupted:
                interrupted = True
                raise ValueError('SYNTHETIC browser interruption before capture')
            return self.inspect(*args, **kwargs)
        first = self.run_worker(run, inspect)
        self.assertEqual(first['status'], 'interrupted', first.get('error'))
        work = git_task.run_folder(self.folder, run)
        head = git(work / 'candidate', 'rev-parse', 'HEAD')
        second = self.run_worker(run)
        self.assertEqual(second['status'], 'ready_review', second.get('error'))
        self.assertEqual(self.inspect_calls, ['0', '1'])
        self.assertEqual(git(work / 'candidate', 'rev-parse', 'HEAD'), head)
        self.assertEqual(len(second['attempts']['attempts']), 1)

    def test_existing_scoped_proposal_can_be_verified_without_duplicate_or_revived_approval(self):
        ref = chat_build.propose_build(self.root, self.folder, 'synthetic-git-bridge', 'Repair counter scoring',
            dict(title='Original pending candidate', summary='SYNTHETIC exact source',
                 files=[dict(path=name, content=text) for name, text in self.candidate.items()]),
            expected_before=chat_build.context(self.root, self.folder)['sha256'])
        origin = dict(proposal_ref=ref)
        wrong = {**self.candidate, 'style.css': self.candidate['style.css'] + '\n/* different candidate */'}
        with self.assertRaisesRegex(ValueError, 'exact pending'):
            git_task.prepare(self.root, self.folder, candidate_files=wrong, origin=origin)
        run = self.prepare(origin=origin)
        self.approve(run)
        row = self.run_worker(run)
        self.assertEqual(row['status'], 'ready_review', row.get('error'))
        count = len(chat_build.list_requests(self.folder))
        self.assertEqual(git_task.promote(self.root, self.folder, run)['request_ref'], ref)
        self.assertEqual(len(chat_build.list_requests(self.folder)), count)
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])
        self.app.respond(ref, 'decline', 'SYNTHETIC owner rejects the original candidate')
        with self.assertRaisesRegex(ValueError, 'pending proposal'):
            git_task.promote(self.root, self.folder, run)

    def test_recorded_report_recovers_its_allowance_and_status_without_repeating_work(self):
        run = self.prepare(); self.approve(run)
        with patch('ember_harness.git_task.TaskAttempts.finish', side_effect=ValueError('SYNTHETIC interruption after report audit')):
            first = self.run_worker(run)
        self.assertEqual(first['status'], 'interrupted')
        self.assertTrue(first['report']['qualified'])
        self.assertEqual(first['attempts']['attempts'][0]['outcome'], 'running')
        work, h, packet, plan = git_task.load(self.folder, run)
        head = git(work / 'candidate', 'rev-parse', 'HEAD')
        with patch('ember_harness.git_task.subprocess.Popen') as spawn:
            self.app.git_control(self.folder.name, 'resume', run_id=run)
            spawn.assert_called_once()
        second = self.run_worker(run)
        self.assertEqual(second['status'], 'ready_review', second.get('error'))
        self.assertEqual(second['attempts']['attempts'][0]['outcome'], 'qualified')
        self.assertEqual(len(second['attempts']['attempts']), 1)
        self.assertEqual(self.inspect_calls, ['0', '1'])
        self.assertEqual(git(work / 'candidate', 'rev-parse', 'HEAD'), head)
        # The later window, after the allowance receipt but before final status,
        # also replays only finalization and cannot duplicate its audit records.
        (work / 'state.json').unlink()
        self.assertEqual(git_task.history(self.root, self.folder)[-1]['status'], 'interrupted')
        with patch('ember_harness.git_task.subprocess.Popen') as spawn:
            self.app.git_control(self.folder.name, 'resume', run_id=run)
            spawn.assert_called_once()
        third = self.run_worker(run)
        self.assertEqual(third['status'], 'ready_review')
        self.assertEqual(self.inspect_calls, ['0', '1'])
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'git_task_report']), 1)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'task_attempt_started']), 1)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'task_attempt_finished']), 1)
        with patch('ember_harness.git_task.subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'completed result'):
            self.app.git_control(self.folder.name, 'resume', run_id=run)
        spawn.assert_not_called()

    def test_recorded_report_resume_honors_stop_during_final_revalidation(self):
        run = self.prepare(); self.approve(run)
        with patch('ember_harness.git_task.TaskAttempts.finish', side_effect=ValueError('SYNTHETIC interruption after report audit')):
            first = self.run_worker(run)
        self.assertEqual(first['status'], 'interrupted')
        work = git_task.run_folder(self.folder, run)
        original = git_task.completed_report
        def stop_after_verification(*args):
            report = original(*args)
            atomic_json(work / 'stop.json', dict(reason='SYNTHETIC stop during report validation'))
            return report
        with patch('ember_harness.git_task.completed_report', side_effect=stop_after_verification):
            row = self.run_worker(run)
        self.assertEqual(row['status'], 'stopped')
        self.assertEqual(row['attempts']['attempts'][0]['outcome'], 'stopped')
        self.assertEqual(self.inspect_calls, ['0', '1'])

    @unittest.skipUnless(shutil.which('node'), 'Optional Node runtime required for real fixed-step observations')
    def test_canonical_mechanic_runtime_downgrade_cannot_qualify_on_positive_dom_checks(self):
        from test_mechanic_evidence import Observations
        baseline = mechanic_recipes.reference_files()
        self.candidate = {**baseline, 'mechanic-runtime.js': baseline['mechanic-runtime.js'] + '\n// SYNTHETIC noncanonical runtime edit'}
        run = self.prepare(baseline_files=baseline); self.approve(run)
        def dom_result(source, data, report):
            report['gameplay'] = checks.result(data['gameplay_plan'], failed=source.parent.name == '0')
        observed = Observations(dom_result)
        row = self.run_worker(run, inspect=observed)
        self.assertEqual(row['status'], 'needs_changes', row.get('error'))
        report = row['report']
        self.assertEqual(report['before']['gameplay']['outcome'], 'failed')
        self.assertEqual(report['after']['gameplay']['outcome'], 'passed')
        self.assertFalse(report['qualified'])
        self.assertTrue(report['mechanics']['blockers'])
        self.assertIn('Restore its canonical runtime', report['reason'])
        self.assertIsNotNone(observed.inputs[0][1].get('mechanic_binding'))
        self.assertIsNone(observed.inputs[1][1].get('mechanic_binding'))
        self.assertEqual(git_task.load(self.folder, run)[3]['mechanics'], mechanic_workflow.binding(baseline))
        self.assertEqual(git_task.completed_report(self.folder, run), report)
        with self.assertRaisesRegex(ValueError, 'qualifying'):
            git_task.promote(self.root, self.folder, run)

    @unittest.skipUnless(os.name == 'nt', 'Windows Git reference-path limit')
    def test_deep_project_root_refuses_before_creating_private_git_metadata(self):
        scratch = self.root / ('long-project-name-' * 5)
        scratch.mkdir()
        real_temp = builds.tempfile.TemporaryDirectory
        def deep_temp(*args, **kwargs):
            return real_temp(*args, **{**kwargs, 'dir': scratch})
        nested = tasks.TaskRunTests()
        with patch('test_chat_build.tempfile.TemporaryDirectory', side_effect=deep_temp):
            nested.setUp()
        self.addCleanup(nested.doCleanups)
        self.fixture = nested
        self.root, self.folder, self.app = nested.root, nested.folder, nested.app
        gameplay.save(self.folder, self.plan, 1)
        with self.assertRaisesRegex(ValueError, 'Choose a shorter Ember workspace'):
            self.prepare()
        self.assertFalse((self.folder / 'git-runs').exists())
        self.assertEqual(git_task.requests(self.folder), [])

    def test_git_failure_exposes_bounded_stderr_instead_of_only_command_arguments(self):
        run = self.prepare(); self.approve(run)
        original = git_task.git
        def command(repo, *args):
            if 'commit' in args:
                raise subprocess.CalledProcessError(128, ['SYNTHETIC Git command'], stderr=b'SYNTHETIC precise ref creation failure\n')
            return original(repo, *args)
        with patch('ember_harness.git_task.git', side_effect=command):
            row = self.run_worker(run)
        self.assertEqual(row['status'], 'interrupted')
        self.assertEqual(row['error'], 'Local Git operation failed: SYNTHETIC precise ref creation failure')

    def test_scope_checks_and_runtime_tamper_stop_before_git_creation(self):
        with self.assertRaisesRegex(ValueError, 'Current game changed'):
            self.prepare(expected_manifest={'index.html': 'f' * 64})
        run = self.prepare(); self.approve(run)
        saved = gameplay.load(self.folder)
        gameplay.save(self.folder, {**self.plan, 'title': 'Different checks'}, saved['revision'])
        with self.assertRaisesRegex(ValueError, 'regression plan changed'):
            git_task.Worker(self.root, self.folder, run).run()
        self.assertFalse((git_task.run_folder(self.folder, run) / 'baseline/.git').exists())

    def test_scope_is_non_executable_and_child_git_branch_and_paths_remain_fixed(self):
        run = self.prepare()
        work, h, packet, plan = git_task.load(self.folder, run)
        binding = plan['project_plan']['binding']
        parent = h._authority(h._active(h._entries())[binding['contract_id']], h._active(h._entries()))
        action = dict(agent=parent['agent'], contract_id=parent['id'], tool='git.commit',
            args=dict(branch=plan['branch'], message='Ember Git baseline test'), paths=dict(read=[], write=[]), spend=0)
        self.assertEqual(h.check(action)['reason'], 'scope_is_ceiling_only')
        worker = deepcopy(packet['body']['contracts'][0]['contract'])
        stage = next(a for a in worker['allowed_actions'] if a['tool'] == 'git.add')
        stage['args_constraints']['branch'] = dict(pattern=git_task.BRANCH)
        with self.assertRaisesRegex(ValueError, 'fixed branch'):
            validate(worker)
        worker = deepcopy(packet['body']['contracts'][0]['contract'])
        stage = next(a for a in worker['allowed_actions'] if a['tool'] == 'git.add')
        stage['args_constraints']['branch'] = dict(equals='round/2/unapproved')
        self.assertFalse(subset(worker, parent))
        stage['args_constraints']['branch'] = dict(equals=plan['branch'])
        stage['args_constraints']['path'] = dict(equals=(self.root / 'outside-git-run').as_posix())
        self.assertFalse(subset(worker, parent))

    def test_preplanted_git_worktree_redirection_is_refused_before_any_git_command(self):
        run = self.prepare(); self.approve(run)
        work = git_task.run_folder(self.folder, run)
        repo = work / 'baseline'; repo.mkdir()
        template = self.root / 'empty-git-template'; template.mkdir()
        git(repo, 'init', '--template=' + str(template))
        outside = self.root / 'outside-source'; outside.mkdir()
        sentinel = outside / 'index.html'; sentinel.write_text('ORIGINAL OUTSIDE SOURCE', encoding='utf-8')
        with (repo / '.git/config').open('a', encoding='utf-8') as stream:
            stream.write('\tworktree = ' + outside.as_posix() + '\n')
        with self.assertRaisesRegex(ValueError, 'fixed host-created'):
            git_task._metadata(repo)
        with patch('ember_harness.git_task.git') as commands:
            row = self.run_worker(run)
            commands.assert_not_called()
        self.assertEqual(row['status'], 'interrupted')
        self.assertIn('preexisting Git metadata', row['error'])
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'ORIGINAL OUTSIDE SOURCE')
        self.assertFalse((repo / '.git/index').exists())
        self.assertEqual(set(outside.iterdir()), {sentinel})

    def test_private_http_review_resume_and_promotion_never_apply_implicitly(self):
        http = server(self.app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 5); self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        base = f'http://127.0.0.1:{http.server_port}/api/'
        def post(endpoint, body, auth=True):
            headers = {'Content-Type': 'application/json'}
            if auth:
                headers['X-Ember-Token'] = self.app.token
            with urlopen(Request(base + endpoint, json.dumps(body).encode(), headers)) as response:
                return json.load(response)
        def get(endpoint, auth=True, **query):
            headers = {'X-Ember-Token': self.app.token} if auth else {}
            with urlopen(Request(base + endpoint + '?' + urlencode(query), headers=headers)) as response:
                return response.read()
        current = chat_build.context(self.root, self.folder)['manifest']
        body = dict(session_id=self.folder.name, action='prepare', goal='Repair two-point counter reward',
            path='app.js', before=' + 1;', after=' + 2;', expected_manifest=current)
        with self.assertRaises(HTTPError) as denied:
            post('git-task', body, auth=False)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(HTTPError) as denied:
            post('git-task', {**body, 'session_id': 'f' * 24})
        self.assertEqual(denied.exception.code, 400)
        prepared = post('git-task', body)
        run = prepared['id']; work = git_task.run_folder(self.folder, run)
        self.assertFalse((work / 'baseline/.git').exists())
        with self.assertRaises(HTTPError) as denied:
            get('git-preview', auth=False, session_id=self.folder.name, run_id=run)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(HTTPError) as denied:
            post('git-task', dict(session_id=self.folder.name, action='resume', run_id=run))
        self.assertEqual(denied.exception.code, 400)
        def launched(*args, **kwargs):
            git_task.Worker(*args).check()
            atomic_json(work / 'state.json', dict(status='running', phase='SYNTHETIC background launch', error=None))
            return dict(status='running', id=run)
        owner = dict(ref=prepared['request_ref'], choice='approve', quote='SYNTHETIC HTTP exact Git permissions')
        with patch('ember_harness.git_task.launch', side_effect=launched) as launch:
            post('decide', owner); post('decide', owner)
            self.assertEqual(launch.call_count, 1)
            row = self.run_worker(run)
            self.assertEqual(row['status'], 'ready_review', row.get('error'))
            self.assertIn(b'data:text/javascript;base64', get('git-preview', session_id=self.folder.name, run_id=run))
            self.assertTrue(get('git-image', session_id=self.folder.name, run_id=run, stage='candidate', name='mobile').startswith(b'\x89PNG'))
            with self.assertRaises(HTTPError) as denied:
                get('git-preview', session_id='f' * 24, run_id=run)
            self.assertEqual(denied.exception.code, 400)
            post('git-task', dict(session_id=self.folder.name, action='promote', run_id=run))
            self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])
            self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], current)
            post('decide', owner)
            self.assertEqual(launch.call_count, 1)


class SafeGitTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows Git reference-path limit')
    def test_windows_path_prerequisite_counts_utf16_code_units(self):
        branch = 'round/1/ct-git-worker-' + 'a' * 24 + '-0001'
        git_task._check_git_paths(Path('C:/short'), branch)
        with self.assertRaisesRegex(ValueError, 'Choose a shorter Ember workspace'):
            git_task._check_git_paths(Path('C:/' + '\U0001f525' * 85), branch)

    def test_git_ignores_inherited_redirection_config_and_helpers(self):
        captured = {}
        def process(command, **kwargs):
            captured.update(command=command, **kwargs)
            return subprocess.CompletedProcess(command, 0, stdout=b'fixed')
        with patch.dict(os.environ, {'GIT_DIR': '/other', 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor', 'GIT_CONFIG_VALUE_0': 'untrusted'}), patch('ember_harness.contract_lock.subprocess.run', side_effect=process):
            self.assertEqual(git('/private', 'status', '--porcelain'), b'fixed')
        self.assertNotIn('GIT_DIR', captured['env'])
        self.assertNotIn('GIT_CONFIG_COUNT', captured['env'])
        self.assertEqual(captured['env']['GIT_ALLOW_PROTOCOL'], '')
        self.assertIn('core.fsmonitor=false', captured['command'])
        self.assertIn('protocol.allow=never', captured['command'])
        self.assertEqual(captured['timeout'], 30)
