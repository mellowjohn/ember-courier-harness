// Installed-launch rehearsal. No fixture server, model responses or owner approvals.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.EMBER_PLAYWRIGHT_MODULE);

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}}), errors=[];
    page.setDefaultTimeout(30000);
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    const title = page.locator('#session-title');
    const home = page.locator('#home-screen');
    const create = home.getByRole('button',{name:'Create a session',exact:true});
    const recent = home.locator('#home-sessions').getByRole('button',{name:/Desktop launch rehearsal/});
    await home.getByRole('heading',{name:'Your game studio',exact:true}).waitFor();
    await page.locator('#home-create:not([disabled])').waitFor();
    assert(await title.isHidden());
    for (const id of ['save','workspace-tools-open','tester-agent-open','connection-error']) {
      assert(await page.locator('#'+id).isHidden());
    }
    const firstLaunch = process.env.EMBER_LAUNCH_PHASE === 'create';
    await (firstLaunch ? home.getByText('No sessions yet',{exact:true}) : recent).waitFor();
    for (const [name,width,height] of [['desktop',1500,1000],['mobile',390,844]]) {
      await page.setViewportSize({width,height});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'home-'+process.env.EMBER_LAUNCH_PHASE+'-'+name+'.png')});
    }
    await page.setViewportSize({width:1500,height:1000});
    if (firstLaunch) {
      await create.click();
      await page.locator('#session-name').fill('Desktop launch rehearsal');
      await page.locator('#project-parent').fill(process.env.EMBER_PROJECT_PARENT);
      await page.getByRole('button',{name:'Create session',exact:true}).click();
      await page.waitForFunction(()=>!document.querySelector('#start').disabled &&
        document.querySelector('#session-title').textContent==='Desktop launch rehearsal');
      await require('./workspace_browser').view(page,'plan');
      // Seed guidance through the retained local API; this installed-launch check makes no model call.
      await page.evaluate(async()=>{await api('project-brief',{session_id:activeSession.id,revision:0,
        fields:{goal:'Original offline courier game',controls:'Arrow keys and touch',visual_direction:'',constraints:''}});await refresh()});
      await page.locator('#brief-answers').getByText('Original offline courier game',{exact:true}).waitFor();
    } else {
      await recent.click();
      await page.waitForFunction(()=>!busy && document.querySelector('#session-title').textContent==='Desktop launch rehearsal');
      await require('./workspace_browser').view(page,'plan');
      await page.locator('#brief-answers').getByText('Original offline courier game',{exact:true}).waitFor();
      await page.locator('#brief-answers').getByText('Arrow keys and touch',{exact:true}).waitFor();
      // The remembered project location also seeds the next session dialog.
      await require('./workspace_browser').view(page,'chat');
      await page.getByRole('button',{name:'New session',exact:true}).click();
      assert.equal(await page.locator('#project-parent').inputValue(),process.env.EMBER_PROJECT_PARENT);
      await page.getByRole('button',{name:'Cancel',exact:true}).click();
    }
    await title.filter({hasText:'Desktop launch rehearsal'}).waitFor();
    await require('./workspace_browser').view(page,'chat');
    await page.getByRole('button',{name:'Home',exact:true}).click();
    await recent.waitFor();
    assert(await title.isHidden());
    await recent.click();
    await title.waitFor();
    assert.equal(new URL(page.url()).hash,'');
    assert.equal((await page.request.get(process.env.EMBER_BROWSER_URL+'api/state')).status(),403);
    for (const [name,width,height] of [['desktop',1500,1000],['mobile',390,844]]) {
      await page.setViewportSize({width,height});
      for (const tab of ['plan','chat','playtest','report']) {
        await require('./workspace_browser').view(page,tab);
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      }
      await require('./workspace_browser').view(page,'plan');
      await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,process.env.EMBER_LAUNCH_PHASE+'-'+name+'.png')});
    }
    assert.deepEqual(errors,[]);
    assert.equal(await page.locator('#error').textContent(),'');
    assert(await page.locator('#connection-error').isHidden());
    fs.writeFileSync(path.join(process.env.EMBER_BROWSER_OUTPUT,process.env.EMBER_LAUNCH_PHASE+'-observations.json'),
      JSON.stringify({passed:true,phase:process.env.EMBER_LAUNCH_PHASE,viewports:['desktop','mobile'],pageErrors:errors},null,2));
    process.stdout.write('PASS: installed launcher, session UI, saved brief and desktop/mobile navigation\n');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
