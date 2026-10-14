// Tests the public browser -> HTTPS ingress -> GPU -> transcript -> download flow.
// Microphone audio is synthetic; the user's microphone is never accessed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const url = process.env.PROTOTYPE_URL || 'https://whisper.speeches.dev';
const root = __dirname;
(async () => {
  const browser = await chromium.launch({headless:true,args:[
    '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.join(root,'evidence/jfk.wav')}`,
  ]});
  const report = {tested_at:new Date().toISOString(),url,results:{},public_fixture_transcript:''};
  const context = await browser.newContext({permissions:['microphone','clipboard-read','clipboard-write']});
  const page = await context.newPage();
  const scriptErrors=[];page.on('pageerror',e=>scriptErrors.push(e.message));
  const idle = () => page.waitForFunction(()=>!document.getElementById('clear').disabled,{},{timeout:45000});
  try {
    await page.goto(url);await page.getByText('CPU-Nachweis lokal geprüft · GPU bereit',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>window.isSecureContext),true);
    const runtime=await (await context.request.get(url+'/v1/runtime')).json();
    assert.equal(runtime.confidential_computing,false);
    assert.equal(runtime.attestation_verified,false);
    assert.equal(runtime.cpu_tee,'AMD SEV-SNP');
    assert.equal(runtime.gpu_confidential_computing,false);
    assert.equal(await page.locator('#record').isDisabled(),true);
    assert.equal(await page.locator('#audio-file').isDisabled(),true);
    const attestation=JSON.parse(await page.locator('#report-data').textContent());
    assert.equal(attestation.cpu_guest_verified,true);
    assert.equal(attestation.session_key_bound,true);
    report.results.local_cpu_attestation_and_confirmation_gate='passed';
    report.results.secure_browser_context_and_honest_runtime='passed';
    await page.locator('#consent').check();await page.locator('#language').selectOption('en');
    await page.locator('#record').click();
    await page.getByRole('button',{name:'Aufnahme beenden'}).waitFor();
    await page.waitForFunction(()=>document.getElementById('timer').textContent==='00:12',{},{timeout:20000});
    await page.locator('#record').click();await idle();
    const live=await page.locator('#transcript').inputValue();
    assert(live.toLowerCase().includes('what you can do'),live);
    assert((live.toLowerCase().match(/country/g)||[]).length>=2,live);
    report.public_fixture_transcript=live;
    report.results.full_live_recording_including_final_partial_chunk='passed';
    await page.locator('#transcript').fill(live+'\nManuell bearbeitet.');
    await page.locator('#copy').click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),live+'\nManuell bearbeitet.');
    report.results.edit_and_copy='passed';
    const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();
    const download=await downloadPromise;
    let contents='';for await(const part of await download.createReadStream()) contents+=part.toString();
    assert.equal(contents,live+'\nManuell bearbeitet.');
    report.results.download_contents='passed';
    await page.locator('#clear').click();
    let failNext=true;
    await page.route('**/v1/audio/transcriptions',route=>{
      if(failNext){failNext=false;return route.abort('connectionreset');}
      return route.continue();
    });
    await page.locator('#record').click();
    await page.waitForFunction(()=>document.getElementById('status').textContent.includes('bestätige erneut'),{},{timeout:25000});
    assert.equal(await page.locator('#record').isDisabled(),true);
    await page.locator('#check').click();await page.getByText('CPU-Nachweis lokal geprüft · GPU bereit',{exact:true}).waitFor();await page.locator('#consent').check();await idle();
    assert((await page.locator('#transcript').inputValue()).toLowerCase().includes('country'));
    assert.equal(await page.locator('#record').isEnabled(),true);
    report.results.failed_live_chunk_preserved_and_retried='passed';
    await page.unroute('**/v1/audio/transcriptions');
    await page.locator('#clear').click();await page.locator('#language').selectOption('de');
    await page.locator('#audio-file').setInputFiles(path.join(root,'evidence/german.wav'));
    await page.waitForFunction(()=>document.getElementById('transcript').value.toLowerCase().includes('aufnahme'),{},{timeout:45000});
    await idle();
    report.results.german_audio_upload='passed';
    report.german_synthetic_transcript=await page.locator('#transcript').inputValue();
    await page.locator('#clear').click();
    await page.locator('#audio-file').setInputFiles({name:'bad.wav',mimeType:'audio/wav',buffer:Buffer.from('not audio')});
    await page.waitForFunction(()=>document.getElementById('status').textContent.includes('fehlgeschlagen'),{},{timeout:15000});
    assert.equal(await page.locator('#audio-file').isEnabled(),true);
    report.results.invalid_upload_and_recovery='passed';
    const denied=await browser.newContext();
    await denied.addInitScript(()=>{
      navigator.mediaDevices.getUserMedia=()=>Promise.reject(new DOMException('Denied for test','NotAllowedError'));
    });
    const deniedPage=await denied.newPage();await deniedPage.goto(url);
    await deniedPage.getByText('CPU-Nachweis lokal geprüft · GPU bereit',{exact:true}).waitFor();
    await deniedPage.locator('#consent').check();await deniedPage.locator('#record').click();
    await deniedPage.getByText('Mikrofonzugriff wurde nicht erlaubt.',{exact:false}).waitFor();
    assert.equal(await deniedPage.locator('#record').isEnabled(),true);
    assert.equal(await deniedPage.locator('#audio-file').isEnabled(),true);
    report.results.simulated_microphone_permission_denial='passed';
    await denied.close();
    assert.deepEqual(scriptErrors,[]);report.results.browser_script_errors='none';
    fs.writeFileSync(path.join(root,'evidence/cpu-tee-public-flow.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
