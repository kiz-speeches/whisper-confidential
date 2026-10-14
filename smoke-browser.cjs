// End-to-end test with a public fixture and a synthetic microphone, never the user's microphone.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = __dirname;
const url = process.env.PROTOTYPE_URL || 'http://127.0.0.1:8780';
(async () => {
  const browser = await chromium.launch({headless:true,args:[
    '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.join(root,'evidence/jfk.wav')}`,
  ]});
  const context = await browser.newContext({viewport:{width:1280,height:1000},permissions:['microphone']});
  const page = await context.newPage();
  const errors = []; page.on('pageerror',error=>errors.push(error.message));
  try {
    const report = {tested_at:new Date().toISOString(), url, results:{}};
    await page.goto(url); await page.getByText('Whisper auf GPU erreichbar',{exact:true}).waitFor();
    assert.equal(await page.locator('#record').isDisabled(),true);
    assert.equal(await page.locator('#audio-file').isDisabled(),true);
    report.results.confirmation_gate = 'passed';
    await page.locator('#consent').check(); await page.locator('#language').selectOption('en');
    await page.locator('#audio-file').setInputFiles(path.join(root,'evidence/jfk.flac'));
    await page.waitForFunction(()=>document.getElementById('transcript').value.toLowerCase().includes('country'),{},{timeout:60000});
    await page.waitForFunction(()=>!document.getElementById('clear').disabled);
    report.results.upload_transcription = 'passed';
    await page.screenshot({path:path.join(root,'evidence/desktop.png'),fullPage:true});
    await page.locator('#clear').click();
    await page.locator('#record').click();
    await page.getByRole('button',{name:'Aufnahme beenden'}).waitFor();
    await page.waitForFunction(()=>document.getElementById('transcript').value.toLowerCase().includes('country'),{},{timeout:45000});
    await page.locator('#record').click();
    await page.waitForFunction(()=>!document.getElementById('clear').disabled,{},{timeout:30000});
    report.results.synthetic_microphone_live_transcription = 'passed';
    assert.equal(await page.getByRole('button',{name:'Aufnahme starten'}).isEnabled(),true);
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloadPromise;
    assert.match(download.suggestedFilename(),/^transkript-.*\.txt$/);
    report.results.transcript_download = 'passed';
    const invalid = await context.request.post(`${url}/v1/audio/transcriptions`,{multipart:{file:{name:'invalid.wav',mimeType:'audio/wav',buffer:Buffer.from('not audio')}}});
    assert.equal(invalid.status(),400); report.results.invalid_audio_rejected = 'passed';
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(root,'evidence/mobile.png'),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    assert.equal(overflow,false); report.results.mobile_no_horizontal_overflow='passed';
    assert.deepEqual(errors,[]); report.results.browser_errors='none';
    fs.writeFileSync(path.join(root,'evidence/browser-smoke.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
