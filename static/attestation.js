'use strict';
window.teeClient = (() => {
  const utf8 = new TextEncoder(), domain='whisper-cpu-tee-v1';
  let session, loading;
  const bytes = value => Uint8Array.from(atob(value), c=>c.charCodeAt(0));
  const b64 = value => {
    const data = new Uint8Array(value);let text='';
    for(let i=0;i<data.length;i+=32768) text+=String.fromCharCode(...data.subarray(i,i+32768));
    return btoa(text);
  };
  const join = (...parts) => {const out=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));let at=0;for(const p of parts){out.set(p,at);at+=p.length;}return out;};
  async function verifier(){
    if(!loading) loading=(async()=>{
      const go = new Go();
      const response=await fetch('/static/attestation/verifier.wasm');
      if(!response.ok) throw new Error('Lokaler CPU-Prüfer konnte nicht geladen werden.');
      const wasm=await WebAssembly.instantiate(await response.arrayBuffer(),go.importObject);
      void go.run(wasm.instance);
      if(typeof window.verifySnpEvidence!=='function') throw new Error('CPU-Prüfer nicht verfügbar.');
    })();
    return loading;
  }
  async function attest(){
    session=undefined;
    const nonce=crypto.getRandomValues(new Uint8Array(32));
    const key=await crypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
    const clientPub=new Uint8Array(await crypto.subtle.exportKey('raw',key.publicKey));
    await verifier();
    const policyResponse=await fetch('/static/attestation-policy.json',{cache:'no-store'});
    if(!policyResponse.ok) throw new Error('CPU-Prüfpolicy nicht verfügbar.');
    const policy=await policyResponse.json();
    const response=await fetch('/v1/attestation',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nonce:b64(nonce),client_public_key:b64(clientPub)}),signal:AbortSignal.timeout(60000)});
    if(!response.ok) throw new Error(`CPU-Nachweis nicht verfügbar (${response.status}).`);
    const quote=await response.json();
    if(!/^[a-f0-9]{32}$/.test(quote.session_id)) throw new Error('Ungültige Sitzung.');
    const sid=Uint8Array.from(quote.session_id.match(/../g),v=>parseInt(v,16));
    const serverPub=bytes(quote.server_public_key);
    const binding=new Uint8Array(await crypto.subtle.digest('SHA-256',join(utf8.encode(domain+'\0'),nonce,serverPub,clientPub,sid)));
    const expected=Array.from(binding,v=>v.toString(16).padStart(2,'0')).join('');
    // No server-provided "verified" flag is trusted. Signature, AMD chain,
    // signed CRL, challenge, CPU measurement/policy/TCB are checked here.
    const result=JSON.parse(window.verifySnpEvidence(JSON.stringify(quote.evidence),expected,policy.measurement));
    if(!result.verified) throw new Error('CPU-Nachweis ungültig: '+result.error);
    const peer=await crypto.subtle.importKey('raw',serverPub,{name:'ECDH',namedCurve:'P-256'},false,[]);
    const shared=await crypto.subtle.deriveBits({name:'ECDH',public:peer},key.privateKey,256);
    const hkdf=await crypto.subtle.importKey('raw',shared,'HKDF',false,['deriveKey']);
    const derive=direction=>crypto.subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt:nonce,info:utf8.encode(domain+'/'+direction)},hkdf,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
    session={id:quote.session_id,request:await derive('request'),response:await derive('response'),sequence:0,
      expires:Date.now()+Math.min(quote.expires_in,1800)*1000};
    // The GPU is not attested in this prototype. Ignore server claims of GPU verification.
    return {...result,checked_locally_at:new Date().toISOString(),cpu_guest_verified:true,session_key_bound:true,
      verification_scope:'cpu_guest_and_session_key',full_attestation_verified:false,
      gpu_confidential_computing:false,workload_policy_verified:false,
      gpu_attestation:{status:'not_available',placeholder:true,evidence:null,verified:false,confidential_computing:false},
      software_release:{manifest:quote.software_release?.manifest??null,verified:false,binding:'not_attested_to_workload'},
      amd_report:quote.evidence,report_data:expected};
  }
  async function send(blob,language){
    if(!session || Date.now()>=session.expires) throw new Error('CPU-Sitzung abgelaufen. Fordere einen neuen Nachweis an.');
    const current=session,sequence=current.sequence++,iv=crypto.getRandomValues(new Uint8Array(12));
    const aad=utf8.encode(`${domain}/request|${current.id}|${sequence}|${language}`);
    const body=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad},current.request,await blob.arrayBuffer());
    const response=await fetch('/v1/audio/transcriptions',{method:'POST',headers:{'Content-Type':'application/octet-stream',
      'X-Session':current.id,'X-IV':b64(iv),'X-Sequence':String(sequence),'X-Language':language},body,signal:AbortSignal.timeout(120000)});
    if(!response.ok) throw new Error(`Transkription fehlgeschlagen (${response.status}).`);
    const encrypted=await response.json();
    const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes(encrypted.iv),
      additionalData:utf8.encode(`${domain}/response|${current.id}|${sequence}`)},current.response,bytes(encrypted.ciphertext));
    return JSON.parse(new TextDecoder().decode(clear));
  }
  return {attest,send};
})();
