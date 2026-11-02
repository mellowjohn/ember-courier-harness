// Real Web Audio graph output and desktop/mobile controls; no model calls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE||'playwright');
const output=path.resolve(process.argv[2]);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const report={passed:false,viewports:[],signals:{}};
  try {
    for(const [name,viewport] of [['desktop',{width:1280,height:1000}],['mobile',{width:390,height:844}]]) {
      const page=await browser.newPage({viewport,hasTouch:name==='mobile'}),errors=[];
      page.on('pageerror',error=>errors.push(String(error)));
      await page.addInitScript(()=>{
        const Native=window.AudioContext;
        window.__contexts=[];
        window.AudioContext=class extends Native {
          constructor(...args){
            super(...args);window.__contexts.push(this);
            const create=this.createDynamicsCompressor.bind(this);
            this.createDynamicsCompressor=()=>{
              const node=create(),analyser=this.createAnalyser();analyser.fftSize=2048;
              // The probe observes the actual compressor signal sent to the speakers.
              node.connect(analyser);window.__probe={context:this,analyser};return node;
            };
          }
        };
      });
      await page.goto(pathToFileURL(path.join(output,'sound-garden.html')).href);
      assert.equal(await page.evaluate(()=>window.__contexts.length),0,'No context before a player gesture');
      await page.locator('#start').click();await page.waitForFunction(()=>soundDemo.diagnostics().state==='running');
      await page.locator('#stop').click();
      const signal=async()=>{
        const peaks=[];
        for(let i=0;i<5;i++) {
          await page.waitForTimeout(15);
          peaks.push(await page.evaluate(()=>{
            const {analyser}=window.__probe,data=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(data);
            return Math.sqrt(data.reduce((sum,x)=>sum+x*x,0)/data.length);
          }));
        }
        return Math.max(...peaks);
      };
      for(const cue of ['jump','land','pickup','hit','attack','footstep','win','lose','ui']) {
        await page.locator('[data-cue="'+cue+'"]').click();
        const rms=await signal(); assert(rms>.00001,name+' '+cue+' must produce real audio');
        report.signals[name+':'+cue]=rms;
      }
      await page.locator('#stop').click();
      for(const track of ['courier','explore','tension']) {
        await page.locator('#music').selectOption(track); const rms=await signal();
        assert(rms>.00001,name+' '+track+' must produce music');report.signals[name+':'+track]=rms;
      }
      await page.locator('#music').selectOption('');
      for(const ambience of ['wind','embers']) {
        await page.locator('#ambience').selectOption(ambience);await page.waitForTimeout(300);
        const rms=await signal();assert(rms>.00001,name+' '+ambience+' must produce ambience');report.signals[name+':'+ambience]=rms;
      }
      const mute=page.getByRole('button',{name:'Mute',exact:true});await mute.click();await page.waitForTimeout(500);
      assert((await signal())<.00001,'Muted output must be silent');
      await page.getByRole('button',{name:'Unmute',exact:true}).click();await page.waitForTimeout(150);
      assert((await signal())>.00001,'Unmute restores output');
      const musicVolume=page.getByRole('slider',{name:'Music volume'});
      await musicVolume.fill('0.41');assert.equal(await page.evaluate(()=>soundDemo.diagnostics().volumes.music),.41);
      await page.locator('#pause').click();await page.waitForFunction(()=>soundDemo.diagnostics().state==='suspended');
      await page.getByRole('button',{name:'Resume',exact:true}).click();await page.waitForFunction(()=>soundDemo.diagnostics().state==='running');
      await page.locator('#stop').click();await page.waitForTimeout(150);
      assert.equal(await page.evaluate(()=>soundDemo.diagnostics().activeVoices),0);
      assert((await signal())<.00001,'Stopping releases actual audio output');
      assert.equal(await page.locator('#score').textContent(),'Parcels delivered: 1');
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow');
      await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
      assert.deepEqual(errors,[]);report.viewports.push({name,errors});await page.close();
    }
    // Render actual audio into a WAV for quick listening, using the same runtime.
    const render=await browser.newPage();
    await render.goto(pathToFileURL(path.join(output,'sound-garden.html')).href);
    const samples=await render.evaluate(async()=>{
      const context=new OfflineAudioContext(1,44100*9,44100);
      Object.defineProperty(context,'state',{get:()=> 'running'});
      context.resume=async()=>{};
      context.close=async()=>{};
      window.AudioContext=function(){return context;};
      const audio=EmberAudio.create();await audio.unlock();
      // Offline clock scheduling uses bounded calls with a fixed time offset.
      let offset=0;
      Object.defineProperty(context,'currentTime',{get:()=>offset});
      const cues=['ui','footstep','jump','land','pickup','attack','hit','win','lose'];
      for(const cue of cues){audio.play(cue);offset+=.85;}
      const buffer=await context.startRendering();
      const result=Array.from(buffer.getChannelData(0));audio.dispose();return result;
    });
    const wav=Buffer.alloc(44+samples.length*2);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);
    wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(44100,24);
    wav.writeUInt32LE(88200,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples.length*2,40);
    samples.forEach((x,i)=>wav.writeInt16LE(Math.round(Math.max(-1,Math.min(1,x))*32767),44+i*2));
    assert(samples.some(x=>Math.abs(x)>.001),'Rendered WAV must contain a signal');
    fs.writeFileSync(path.join(output,'game-cues.wav'),wav);
    report.passed=true;fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    console.log('Desktop/mobile: all nine cues, three music loops, two ambiences, mute, volumes, pause, stop and actual audio signals passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
