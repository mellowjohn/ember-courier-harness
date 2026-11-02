// Real local approvals with controlled network delays; no model requests.
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require(process.env.EMBER_PLAYWRIGHT_MODULE || 'playwright');

const gate = () => { let release; const wait = new Promise(resolve => {release = resolve}); return {wait, release}; };

(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.EMBER_BROWSER_EXECUTABLE ? {executablePath:process.env.EMBER_BROWSER_EXECUTABLE} : {})});
  const barriers = [];
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}}), errors = [];
    page.setDefaultTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    const loading = page.locator('#build-loading'), frame = page.frameLocator('iframe[title="Approved browser prototype"]');
    const approve = page.getByRole('button',{name:'Approve & play',exact:true});
    await approve.waitFor();
    await frame.getByRole('button',{name:'Start',exact:true}).click();
    assert.equal(await frame.locator('#score').textContent(),'1');
    await page.evaluate(() => {window.originalGameFrame = document.querySelector('iframe[title="Approved browser prototype"]')});

    // A failed approval must clear the cover and preserve the live original game.
    const denied = gate(); barriers.push(denied);
    await page.route('**/api/decide', async route => {await denied.wait; await route.fulfill({status:400,json:{error:'SYNTHETIC approval failure'}})});
    await approve.click();
    await loading.getByText('Applying your changes…',{exact:true}).waitFor();
    assert.equal(await page.locator('#build-result').getAttribute('aria-busy'),'true');
    assert.equal(await page.locator('#build-result').evaluate(node=>node.inert),true);
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'applying-changes-desktop.png')});
    denied.release();
    await page.getByText('SYNTHETIC approval failure',{exact:true}).waitFor();
    await loading.waitFor({state:'hidden'});
    assert.equal(await page.evaluate(()=>window.originalGameFrame===document.querySelector('iframe[title="Approved browser prototype"]')),true);
    assert.equal(await frame.locator('#score').textContent(),'1');
    assert.equal(await page.locator('#build-result').evaluate(node=>node.inert),false);
    await page.unroute('**/api/decide');

    // Keep the cover through file application and the preview fetch, until the iframe loads.
    const apply = gate(), preview = gate(), previewRequested = gate(); barriers.push(apply,preview);
    await page.route('**/api/decide',async route=>{await apply.wait;await route.continue()});
    await page.route('**/api/build-preview',async route=>{previewRequested.release();await preview.wait;await route.continue()});
    await approve.click();
    await loading.getByText('Applying your changes…',{exact:true}).waitFor();
    apply.release();await previewRequested.wait;
    await loading.getByText('Opening your updated game…',{exact:true}).waitFor();
    await page.waitForFunction(()=>!busy);
    assert.equal(await loading.isVisible(),true,'Approval completion must not dismiss the preview loading screen');
    preview.release();
    await loading.waitFor({state:'hidden'});
    await frame.locator('body[data-revision="fixed"]').waitFor();
    assert.equal(await page.locator('#build-result').getAttribute('aria-busy'),'false');
    assert.equal(await page.locator('#build-result').evaluate(node=>node.inert),false);
    await page.unroute('**/api/decide');await page.unroute('**/api/build-preview');

    // A preview failure after a real approval must also release the cover and allow retry.
    await page.getByRole('heading',{name:'Second loading fixture',exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
    const failedPreview = gate();barriers.push(failedPreview);
    await page.route('**/api/build-preview',async route=>{await failedPreview.wait;await route.fulfill({status:400,json:{error:'SYNTHETIC preview failure'}})});
    await approve.click();
    await loading.getByText('Opening your updated game…',{exact:true}).waitFor();
    assert.equal(await page.locator('.build-loading-spinner').evaluate(node=>getComputedStyle(node).animationName),'none');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await loading.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'applying-changes-mobile.png')});
    failedPreview.release();
    await page.getByText('SYNTHETIC preview failure',{exact:true}).waitFor();
    await loading.waitFor({state:'hidden'});
    await page.unroute('**/api/build-preview');
    await page.getByRole('button',{name:'Restart game',exact:true}).click();
    await frame.locator('body[data-revision="fixed"]').waitFor();
    assert.equal(await page.locator('#error').textContent(),'');
    assert(errors.every(message=>message==='SYNTHETIC startup failure'),JSON.stringify(errors));
    process.stdout.write('PASS: approval loading, preview readiness, preserved game on rejection, error recovery, mobile layout and reduced motion\n');
  } finally {for(const barrier of barriers)barrier.release();await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
