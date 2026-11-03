const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
try{const page=await browser.newPage({viewport:{width:1500,height:1000},hasTouch:true});page.setDefaultTimeout(60000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const view=id=>require('./workspace_browser').view(page,id),shot=name=>page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,name+'.png')});
 await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
 await page.getByText('Version 1 · Approved and ready to play',{exact:true}).waitFor();
 const finding=process.env.EMBER_GIT_FINDING==='1';
 if(finding){await view('playtest');await page.locator('[data-finding="BUG-0001"]').getByRole('button',{name:'Review Git repair agent',exact:true}).click();}
 else{await view('plan');await page.getByRole('button',{name:'Review automated Git repair',exact:true}).click();}
 await page.waitForFunction(()=>!document.querySelector('#workspace-tools').open);
 await page.getByRole('button',{name:finding?'Start tester agent':'Approve task run',exact:true}).click();
 await page.getByRole('button',{name:'Approve local Git repair',exact:true}).waitFor({timeout:240000});
 assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Approved and ready to play');
 await shot('generated-git-review');await page.reload();
 await page.getByRole('button',{name:'Approve local Git repair',exact:true}).click();
 await view('plan');const card=page.locator('[data-git-run]').last();
 await card.getByRole('button',{name:'Review Git-verified game changes',exact:true}).waitFor({timeout:240000});
 await card.getByRole('button',{name:'Play Git candidate',exact:true}).click();
 const game=card.locator('iframe').contentFrame();await game.getByRole('button',{name:'Collect parcel',exact:true}).click();
 assert.equal(await game.locator('#score').textContent(),'2');await game.getByRole('button',{name:'Restart',exact:true}).click();
 await page.setViewportSize({width:390,height:844});await game.getByRole('button',{name:'Collect parcel',exact:true}).tap();
 assert.equal(await game.locator('#score').textContent(),'2');await game.getByRole('button',{name:'Restart',exact:true}).tap();
 assert.equal(await game.locator('#score').textContent(),'0');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await shot('generated-git-mobile');await page.setViewportSize({width:1500,height:1000});
 await card.getByRole('button',{name:'View Git before / after screenshots',exact:true}).click();
 await page.waitForFunction(()=>{const images=document.querySelectorAll('[data-git-run] img');return images.length===4&&[...images].every(image=>image.complete&&image.naturalWidth>0)});
 await shot('generated-git-evidence');await card.getByRole('button',{name:'Review Git-verified game changes',exact:true}).click();
 await page.getByRole('heading',{name:'Git-verified browser repair',exact:true}).waitFor();
 await page.getByRole('button',{name:'Approve & play',exact:true}).click();await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
 if(finding){await view('playtest');const row=page.locator('[data-finding="BUG-0001"]');await row.getByRole('button',{name:'Review verified closure',exact:true}).click();
  await page.getByRole('button',{name:'Approve bug closure',exact:true}).click();await row.getByText('S2 · closed · Systems Designer · 1 attempts',{exact:true}).waitFor();}
 await view('plan');await page.locator('[data-task-id="task-1"]').getByText('Build applied · outcome needs review',{exact:true}).waitFor();
 await page.reload();await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();await shot('generated-git-applied');
 assert.deepEqual(errors,[]);console.log('PASS: approved source worker → independent review → exact Git permission → clean baseline/head → mouse/touch/restart → exact apply'+(finding?' → explicit canonical C3 closure':'')+'; task acceptance pending');
}finally{await browser.close()}})().catch(error=>{console.error(error);process.exit(1)});
