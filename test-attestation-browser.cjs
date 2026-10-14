// Real CPU evidence and GPU audio over the public browser interface.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const url=process.env.PROTOTYPE_URL||'https://whisper.speeches.dev';
const evidenceDir=process.env.PROTOTYPE_EVIDENCE_DIR||path.join(__dirname,'evidence');
fs.mkdirSync(evidenceDir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true});
 const results={tested_at:new Date().toISOString(),url,results:{}};
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let quote;
  page.on('response',async response=>{if(response.url().endsWith('/v1/attestation')&&response.ok()) quote=await response.json();});
  await page.goto(url);await page.getByText('CPU-Nachweis lokal geprüft · GPU bereit',{exact:true}).waitFor({timeout:90000});
  const displayed=JSON.parse(await page.locator('#report-data').textContent());
  assert.equal(displayed.verified,true);assert.equal(displayed.cpu_guest_verified,true);
  assert.equal(displayed.gpu_confidential_computing,false);assert.equal(displayed.workload_policy_verified,false);
  assert.equal(displayed.verification_scope,'cpu_guest_and_session_key');assert.equal(displayed.full_attestation_verified,false);
  assert.equal(displayed.gpu_attestation.evidence,null);assert.equal(displayed.gpu_attestation.verified,false);
  assert.equal(await page.locator('#record').isDisabled(),true);assert.equal(await page.locator('#audio-file').isDisabled(),true);
  results.results.real_cpu_evidence_verified_locally_and_confirmation_required='passed';
  let sent,received;
  page.on('request',request=>{if(request.url().endsWith('/v1/audio/transcriptions'))sent=request.postDataBuffer();});
  page.on('response',async response=>{if(response.url().endsWith('/v1/audio/transcriptions'))received=await response.json();});
  await page.locator('#consent').check();await page.locator('#language').selectOption('en');
  await page.locator('#audio-file').setInputFiles(path.join(__dirname,'tests/fixtures/jfk.flac'));
  await page.waitForFunction(()=>document.getElementById('transcript').value.toLowerCase().includes('country'),{},{timeout:45000});
  assert(sent&&!sent.subarray(0,4).equals(Buffer.from('fLaC')));assert(received.iv&&received.ciphertext&&!received.text);
  results.results.encrypted_audio_and_transcript_real_gpu='passed';results.transcript=await page.locator('#transcript').inputValue();
  const report=Buffer.from(quote.evidence.report,'base64');
  const original=JSON.parse(await page.locator('#report-data').textContent());
  const verdict=await page.evaluate(({evidence,expected,measurement})=>JSON.parse(window.verifySnpEvidence(JSON.stringify(evidence),expected,measurement)),
    {evidence:quote.evidence,expected:original.report_data,measurement:original.measurement});assert(verdict.verified);
  // Signature-only corruption passes the nonce and measurement checks first.
  report[0x2a0]^=1;const invalid={...quote.evidence,report:report.toString('base64')};
  const rejected=await page.evaluate(({evidence,expected,measurement})=>JSON.parse(window.verifySnpEvidence(JSON.stringify(evidence),expected,measurement)),
    {evidence:invalid,expected:original.report_data,measurement:original.measurement});
  assert.equal(rejected.verified,false);assert.match(rejected.error,/signature invalid/);
  results.results.wasm_rejects_corrupted_hardware_signature='passed';
  await page.locator('summary').click();
  const downloadPromise=page.waitForEvent('download');await page.locator('#report-download').click();
  const download=await downloadPromise;let downloaded='';for await(const chunk of await download.createReadStream())downloaded+=chunk.toString();
  const bundle=JSON.parse(downloaded);assert.equal(bundle.report,quote.evidence.report);assert.equal(bundle.verification.cpu_guest_verified,true);
  assert.equal(bundle.gpu_attestation.evidence,null);assert.equal(bundle.gpu_attestation.verified,false);
  fs.writeFileSync(path.join(evidenceDir,'cpu-attestation-report.json'),downloaded);
  results.results.full_attestation_report_download='passed';
  const gpuClaims=await browser.newPage();
  await gpuClaims.route('**/v1/attestation',async route=>{
   const response=await route.fetch();const body=await response.json();
   body.gpu_attestation={status:'verified',verified:true,confidential_computing:true,evidence:'fabricated GPU evidence'};
   await route.fulfill({response,json:body});
  });
  await gpuClaims.goto(url);await gpuClaims.getByText('CPU-Nachweis lokal geprüft · GPU bereit',{exact:true}).waitFor({timeout:90000});
  const guarded=JSON.parse(await gpuClaims.locator('#report-data').textContent());
  assert.equal(guarded.cpu_guest_verified,true);assert.equal(guarded.full_attestation_verified,false);
  assert.equal(guarded.gpu_attestation.evidence,null);assert.equal(guarded.gpu_attestation.verified,false);
  assert.equal(await gpuClaims.locator('#audio-file').isDisabled(),true);
  results.results.server_gpu_claim_cannot_promote_placeholder='passed';await gpuClaims.close();
  for(const kind of ['nonce','signature','replay']){
   const badPage=await browser.newPage();let audio=0;
   badPage.on('request',r=>{if(r.url().endsWith('/v1/audio/transcriptions'))audio++;});
   await badPage.route('**/v1/attestation',async route=>{
    const response=await route.fetch();const body=await response.json();
    if(kind==='replay')return route.fulfill({response,json:quote});
    const raw=Buffer.from(body.evidence.report,'base64');raw[kind==='nonce'?0x50:0x2a0]^=1;
    body.evidence.report=raw.toString('base64');await route.fulfill({response,json:body});
   });
   await badPage.goto(url);await badPage.getByText('CPU-Nachweis nicht bestätigt',{exact:true}).waitFor({timeout:90000});
   assert.equal(await badPage.locator('#record').isDisabled(),true);assert.equal(await badPage.locator('#consent').isDisabled(),true);
   assert.equal(await badPage.locator('#audio-file').isDisabled(),true);assert.equal(audio,0);
   results.results['ui_blocks_'+kind+'_attack']='passed';await badPage.close();
  }
  await page.screenshot({path:path.join(evidenceDir,'cpu-attestation-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(evidenceDir,'cpu-attestation-mobile.png'),fullPage:true});
  results.results.mobile_layout='passed';assert.deepEqual(errors,[]);results.results.browser_errors='none';
  fs.writeFileSync(path.join(evidenceDir,'cpu-attestation-browser.json'),JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify(results,null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
