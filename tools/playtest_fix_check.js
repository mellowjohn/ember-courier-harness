// Focused browser rehearsal: synthetic speech and Muse replies, real UI and files.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.EMBER_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.EMBER_BROWSER_EXECUTABLE });
  const url = process.env.EMBER_BROWSER_URL + '#' + process.env.EMBER_BROWSER_TOKEN;
  try {
    const unsupported = await browser.newPage();
    await unsupported.addInitScript(() => {
      Object.defineProperty(window, 'SpeechRecognition', { value: undefined });
      Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined });
    });
    await unsupported.goto(url);
    await unsupported.locator('.playtest-notes > summary').click();
    await unsupported.locator('#playtest-notes').waitFor();
    for (const label of ['Dictate chat message', 'Dictate playtest notes'])
      assert(await unsupported.getByRole('button', { name: label, exact: true }).isDisabled());
    assert((await unsupported.locator('#chat-form').textContent()).includes('Dictation is unavailable'));
    await unsupported.close();

    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } }), errors = [], unexpected = [];
    page.setDefaultTimeout(20000);
    page.on('pageerror', error => errors.push(error.message));
    let submitted;
    page.on('request', request => {
      if (request.url().endsWith('/api/playtest-fix') && request.postDataJSON()?.note) submitted = request.postDataJSON();
      if (/\/api\/(finding|task-run)$/.test(request.url())) unexpected.push(request.url());
    });
    await page.addInitScript(() => {
      window.speechInstances = [];
      class FakeSpeech {
        constructor() { this.aborted = false; window.speechInstances.push(this); }
        start() { this.onstart?.(); }
        abort() { this.aborted = true; this.onend?.(); }
        emit(parts) {
          const results = parts.map(([text, final]) => { const result = [{ transcript: text }]; result.isFinal = final; return result; });
          this.onresult?.({ results });
        }
      }
      Object.defineProperty(window, 'SpeechRecognition', { value: FakeSpeech });
    });
    await page.goto(url);
    const chat = page.locator('#chat-input'), notes = page.locator('#playtest-notes');
    await notes.waitFor({ state: 'attached' });
    await page.getByRole('button', { name: 'Tester agent', exact: true }).click();
    assert(await notes.evaluate(n => document.activeElement === n));
    assert(await page.locator('#finding-form').isHidden());
    const emit = parts => page.evaluate(parts => window.speechInstances.at(-1).emit(parts), parts);

    await chat.fill('Please'); await chat.evaluate(n => n.setSelectionRange(n.value.length, n.value.length));
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await emit([['inspect', false]]); assert.equal(await chat.inputValue(), 'Please inspect');
    await emit([['inspect the counter', true]]); assert.equal(await chat.inputValue(), 'Please inspect the counter');
    await page.getByRole('button', { name: 'Stop dictating chat message', exact: true }).click();
    assert(await page.evaluate(() => window.speechInstances.at(-1).aborted));
    assert.equal(await page.locator('#messages .message.user').count(), 0);
    await chat.fill('Edited by hand');
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await chat.fill('My correction');
    await emit([['late result must not replace my correction', true]]);
    assert.equal(await chat.inputValue(), 'My correction');

    await chat.evaluate(n => n.setSelectionRange(0, n.value.length));
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await emit([['', false]]); assert.equal(await chat.inputValue(), 'My correction');
    await page.getByRole('button', { name: 'Stop dictating chat message', exact: true }).click();

    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await page.evaluate(() => window.speechInstances.at(-1).onerror({ error: 'not-allowed' }));
    await page.locator('#chat-form').getByText('Microphone permission was denied. Allow it in your browser or type instead.', { exact: true }).waitFor();
    assert(!(await chat.isDisabled()));
    await chat.fill('x'.repeat(8000));
    await chat.evaluate(n => n.setSelectionRange(n.value.length, n.value.length));
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await emit([['extra words', true]]); assert.equal((await chat.inputValue()).length, 8000);
    await page.getByRole('button', { name: 'Stop dictating chat message', exact: true }).click();
    await chat.fill('');

    // A session switch must abort recognition and ignore the late old callback.
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await page.getByRole('button', { name: 'New session', exact: true }).click();
    await page.locator('#session-name').fill('SYNTHETIC dictation session');
    await page.getByRole('button', { name: 'Create session', exact: true }).click();
    await page.getByRole('heading', { name: 'SYNTHETIC dictation session', exact: true }).waitFor();
    await emit([['old session speech', true]]); assert.equal(await chat.inputValue(), '');
    assert(await page.evaluate(() => window.speechInstances.at(-1).aborted));
    await page.locator('.session-item').filter({ hasText: 'SYNTHETIC browser QA rehearsal' }).click();
    await page.locator('.playtest-notes > summary').click();
    await notes.waitFor();

    // Starting notes dictation ends chat dictation; submission ends notes dictation.
    await page.getByRole('button', { name: 'Dictate chat message', exact: true }).click();
    await page.getByRole('button', { name: 'Dictate playtest notes', exact: true }).click();
    assert(await page.evaluate(() => window.speechInstances.at(-2).aborted));
    await emit([['The game reports a startup error after loading. Keep the counter controls.', true]]);
    assert((await notes.inputValue()).includes('startup error'));
    await page.getByRole('button', { name: 'Find & fix bug', exact: true }).click();
    assert(await page.evaluate(() => window.speechInstances.at(-1).aborted));
    await page.locator('#agent-progress .ember-status-title').getByText('Investigating the reported bug', { exact: false }).waitFor();
    await page.locator('#agent-progress').screenshot({ path: path.join(process.env.EMBER_BROWSER_OUTPUT, 'notes-investigating.png') });
    await page.locator('#agent-progress .ember-status-title').getByText('Preparing the fix', { exact: false }).waitFor();
    await page.getByRole('button', { name: 'Approve & play', exact: true }).waitFor();
    assert.equal(await page.locator('.build-version').textContent(), 'Version 2 · Approved and ready to play');
    await page.getByText('Investigation and repair plan',{exact:true}).click();
    assert((await page.locator('#agent-progress').textContent()).includes('Suspected cause:'));
    assert.deepEqual(await page.locator('#agent-progress [data-kind="edits"] .agent-file').allTextContents(),['app.js']);
    assert.equal(await page.locator('#agent-progress .agent-stages [aria-current="step"]').textContent(),'Review');
    assert.equal(await page.locator('#finding-reviews .panel').count(), 0);
    assert.deepEqual(unexpected, []);
    await page.locator('#agent-progress').screenshot({ path: path.join(process.env.EMBER_BROWSER_OUTPUT, 'notes-fix-review.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('#agent-progress').screenshot({ path: path.join(process.env.EMBER_BROWSER_OUTPUT, 'notes-fix-mobile.png') });
    await page.setViewportSize({ width: 1500, height: 1000 });
    await page.getByRole('button', { name: 'Try proposed changes', exact: true }).click();
    const candidate = page.frameLocator('iframe[title="Proposed browser prototype · not applied"]');
    await candidate.getByRole('button', { name: 'Start', exact: true }).click();
    assert.equal(await candidate.locator('#score').textContent(), '1');
    await page.route('**/api/decide', async route => { await new Promise(resolve => setTimeout(resolve, 700)); await route.continue(); });
    await page.getByRole('button', { name: 'Approve & play', exact: true }).click();
    await page.locator('#agent-progress').getByText('Applying approved fix', { exact: false }).waitFor();
    await page.getByText('Version 3 · Approved and ready to play', { exact: true }).waitFor();
    await page.locator('#agent-progress .ember-status-title').getByText('Fix applied', { exact: true }).waitFor();
    assert.deepEqual(await page.locator('#agent-progress [data-kind="edits"] .agent-file').allTextContents(),['app.js']);
    await page.reload();
    await page.locator('#agent-progress .ember-status-title').getByText('Fix applied', { exact: true }).waitFor();
    const retry = await page.evaluate(async ({ session_id, report_id, token }) => {
      const response = await fetch('/api/playtest-fix', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Ember-Token': token }, body: JSON.stringify({ session_id, report_id }) });
      return response.status;
    }, { session_id: submitted.session_id, report_id: submitted.report_id, token: process.env.EMBER_BROWSER_TOKEN });
    assert.equal(retry, 200);
    assert(errors.every(message => message === 'SYNTHETIC startup failure'), JSON.stringify(errors));
    process.stdout.write('PASS: notes-only scoped fix, transparent states, exact application and simulated speech input\n');
  } finally { await browser.close(); }
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
