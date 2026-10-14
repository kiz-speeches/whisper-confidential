// Local contract tests. CPU verifier and evidence are explicit mocks, never hardware proof.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(__dirname+'/static/attestation.js','utf8');
async function fixture(cpuValid){
  const key=await webcrypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},true,['deriveBits']);
  const server=Buffer.from(await webcrypto.subtle.exportKey('raw',key.publicKey)).toString('base64');
  const evidence={mock:true};let audioRequests=0;
  const window={verifySnpEvidence:()=>JSON.stringify({verified:cpuValid,error:'mock CPU failure',gpu_confidential_computing:true,full_attestation_verified:true})};
  vm.runInNewContext(source,{window,crypto:webcrypto,TextEncoder,Uint8Array,atob,btoa,AbortSignal,
    Go:class{constructor(){this.importObject={};}run(){}},WebAssembly:{instantiate:async()=>({instance:{}})},
    fetch:async url=>{
      if(url.endsWith('.wasm'))return {ok:true,arrayBuffer:async()=>new ArrayBuffer(0)};
      if(url.includes('policy'))return {ok:true,json:async()=>({measurement:'mock measurement'})};
      if(url==='/v1/audio/transcriptions'){audioRequests++;throw new Error('Unexpected audio');}
      return {ok:true,json:async()=>({evidence,session_id:'01'.repeat(16),server_public_key:server,expires_in:1800,
        software_release:{manifest:{version:'untrusted server label'},verified:true},
        gpu_attestation:{verified:true,evidence:'fabricated GPU evidence',confidential_computing:true}})};
    }});
  return {client:window.teeClient,evidence,audioRequests:()=>audioRequests};
}
(async()=>{
  const good=await fixture(true),report=await good.client.attest();
  assert.equal(report.cpu_guest_verified,true);
  assert.equal(report.verification_scope,'cpu_guest_and_session_key');
  assert.equal(report.full_attestation_verified,false);
  assert.equal(report.gpu_confidential_computing,false);
  assert.equal(report.gpu_attestation.evidence,null);
  assert.equal(report.gpu_attestation.verified,false);
  assert.equal(report.software_release.verified,false);
  assert.equal(report.software_release.binding,'not_attested_to_workload');
  assert.equal(report.amd_report,good.evidence);
  const bad=await fixture(false);
  await assert.rejects(bad.client.attest(),/CPU-Nachweis ungültig/);
  await assert.rejects(bad.client.send(new Blob(['audio']),'de'),/CPU-Sitzung abgelaufen/);
  assert.equal(bad.audioRequests(),0);
  console.log('PASS: server GPU claims cannot promote placeholder; invalid CPU blocks audio; AMD evidence unchanged (CPU verifier mocked).');
})().catch(error=>{console.error(error);process.exit(1);});
