// Owned fixture browser, never the user's open browser or a live provider.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
    page.setDefaultTimeout(60000);
    const view=id=>require('./workspace_browser').view(page,id);
    const editChecks=async()=>{await view('playtest');if(await page.locator('#gameplay-form').isHidden())await page.locator('#gameplay-edit').click()};
page.on('pageerror',error=>errors.push(error.message));
    const url=process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN;
    await page.goto(url);await view('assets');await page.locator('#known-assets').waitFor();
    await page.getByRole('heading',{name:process.env.EMBER_ASSET_NAME,exact:true}).waitFor();
    await view('chat');
    async function message(text){await page.locator('#chat-input').fill(text);await page.getByRole('button',{name:'Send message',exact:true}).click();}
    await message('Where is the gate source?');
    await page.locator('.message.assistant').filter({hasText:process.env.EMBER_ASSET_SOURCE}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Accept asset & play',exact:true}).count(),0);
    await page.reload();await page.locator('.message.assistant').filter({hasText:process.env.EMBER_ASSET_SOURCE}).waitFor();
    await page.locator('#chat-send:not([disabled])').waitFor();
    await message('Put it into the scene.');
    await page.getByRole('button',{name:'Accept asset & play',exact:true}).waitFor();
    await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
    const proposed=page.frameLocator('iframe[title="Proposed browser prototype · not applied"]');
    await proposed.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
    assert.equal(await proposed.locator('#asset-name').textContent(),process.env.EMBER_ASSET_NAME);
    await proposed.locator('#approach').click();await proposed.locator('#interact').click();
    assert.equal(await proposed.locator('#lid-state').textContent(),'Open');
    assert.equal(await page.locator('.build-version').count(),0);
    await page.getByRole('button',{name:'Check proposed changes',exact:true}).click();
    await page.getByText('Proposed gameplay checks passed',{exact:true}).waitFor();
    await page.locator('#review').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'asset-chat-proposal.png')});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await view('chat');
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'asset-chat-mobile.png')});
    await page.setViewportSize({width:1500,height:1000});
    await page.getByRole('button',{name:'Accept asset & play',exact:true}).click();
    await page.getByText('Version 1 · Approved and ready to play',{exact:true}).waitFor();
    const current=page.frameLocator('iframe[title="Approved browser prototype"]');
    await current.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
    await current.locator('#approach').click();await current.locator('#interact').click();
    await message('Make the stage background darker.');
    await page.getByRole('button',{name:'Approve & play',exact:true}).waitFor();
    assert.equal(await current.locator('#lid-state').textContent(),'Open');
    assert.equal(await page.getByRole('button',{name:'Accept asset & play',exact:true}).count(),0);
    await page.getByRole('button',{name:'Approve & play',exact:true}).click();
    await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
    await current.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
    assert.equal(await current.locator('#asset-name').textContent(),process.env.EMBER_ASSET_NAME);
    if(process.env.EMBER_ASSET_UPDATE_SOURCE){
      const tracked=process.env.EMBER_ASSET_TRACKED_SOURCE,id=process.env.EMBER_ASSET_ID;
      await current.locator('#approach').click();await current.locator('#interact').click();
      await view('assets');
      // Only the test-owned export is changed. The original artist source stays intact.
      fs.writeFileSync(path.join(tracked,id+'.glb'),'SYNTHETIC invalid export');
      await page.getByRole('button',{name:'Review updated export',exact:true}).click();
      await page.locator('#asset-update-status').filter({hasText:/GLB/i}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Accept asset & play',exact:true}).count(),0);
      assert.equal(await current.locator('#lid-state').textContent(),'Open');
      for(const name of ['asset-spec.json',id+'.glb',id+'.blend'])fs.copyFileSync(path.join(process.env.EMBER_ASSET_UPDATE_SOURCE,name),path.join(tracked,name));
      await page.getByRole('button',{name:'Review updated export',exact:true}).click();
      await view('chat');
      await page.getByRole('button',{name:'Accept asset & play',exact:true}).waitFor();
      assert.equal(await current.locator('#lid-state').textContent(),'Open');
      await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
      await proposed.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
      // Read the package in the exact preview iframe, independently of DOM labels.
      const packageHash=await page.locator('iframe[title="Proposed browser prototype · not applied"]').elementHandle().then(async element=>{
        const frame=await element.contentFrame();return frame.evaluate(()=>EMBER_ASSET.report.sha256);
      });
      assert.equal(packageHash,process.env.EMBER_ASSET_NEW_SHA);
      await page.getByRole('button',{name:'Check proposed changes',exact:true}).click();
      await page.getByText('Proposed gameplay checks passed',{exact:true}).waitFor();
      await page.locator('#review').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'asset-update-proposal.png')});
      await page.reload();await page.getByRole('button',{name:'Accept asset & play',exact:true}).waitFor();
      await page.getByText('Proposed gameplay checks passed',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Accept asset & play',exact:true}).click();
      await page.getByText('Version 3 · Approved and ready to play',{exact:true}).waitFor();
      await current.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
      const approvedFrame=await (await page.locator('iframe[title="Approved browser prototype"]').elementHandle()).contentFrame();
      assert.equal(await approvedFrame.evaluate(()=>EMBER_ASSET.report.sha256),process.env.EMBER_ASSET_NEW_SHA);
    }
    assert.deepEqual(errors,[]);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
