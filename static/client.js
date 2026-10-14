'use strict';
const $ = id => document.getElementById(id);
const transcript = $('transcript');
let checking=false, ready=false, recording=false, starting=false, stopping=false, processing=false;
let stream, context, source, capture, silent, timer, started, lastLanguage, flushDone;
let chunks=[], samples=0, queue=[], completed=0;
let attestationReport;
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function controls(){
  const allowed=ready && $('consent').checked;
  $('check').disabled=checking || recording || starting || stopping || processing;
  $('record').disabled=checking || starting || stopping || (!recording && (!allowed || processing || queue.length>0));
  $('audio-file').disabled=checking || !allowed || recording || starting || stopping || processing || queue.length>0;
  $('language').disabled=recording || starting || stopping || processing || queue.length>0;
  $('consent').disabled=!ready || recording || starting || stopping || processing;
  $('clear').disabled=recording || starting || stopping || processing || queue.length>0 || !transcript.value;
  $('copy').disabled=$('download').disabled=!transcript.value;
  $('word-count').textContent=`${transcript.value.trim()?transcript.value.trim().split(/\s+/).length:0} Wörter`;
}
async function check(){
  checking=true;ready=false;attestationReport=undefined;$('report-download').disabled=true;$('consent').checked=false;$('consent').disabled=true;controls();
  status('CPU-Nachweis wird angefordert und lokal geprüft …');
  try{
    const health=await fetch('/health',{cache:'no-store'});
    if(!health.ok) throw new Error('Whisper ist nicht erreichbar.');
    const h=await health.json();if(!h.ready || h.device!=='cuda') throw new Error('GPU nicht bereit.');
    const report=await teeClient.attest();
    attestationReport=report;$('report-download').disabled=false;
    ready=true;$('connection').textContent='CPU-Nachweis lokal geprüft · GPU bereit';$('connection-dot').className='dot ready';
    const {amd_report,...summary}=report;
    $('report-data').textContent=JSON.stringify(summary,null,2);
    status('CPU-Nachweis gültig. Bestätige die Verarbeitung auf der GPU ohne CC, um zu beginnen.');
  }catch(error){
    ready=false;$('connection').textContent='CPU-Nachweis nicht bestätigt';$('connection-dot').className='dot error';
    $('report-data').textContent=error.message;status(error.message,true);
  }finally{checking=false;controls();$('consent').disabled=!ready;}
}

function merge(parts,length){
  const joined=new Float32Array(length);let offset=0;
  for(const part of parts){joined.set(part,offset);offset+=part.length;}
  return joined;
}
function wav(pcm,rate){
  const target=16000,length=Math.floor(pcm.length*target/rate);
  const buffer=new ArrayBuffer(44+length*2),view=new DataView(buffer);
  const text=(at,s)=>[...s].forEach((c,i)=>view.setUint8(at+i,c.charCodeAt(0)));
  text(0,'RIFF');view.setUint32(4,36+length*2,true);text(8,'WAVE');text(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,target,true);view.setUint32(28,target*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  text(36,'data');view.setUint32(40,length*2,true);
  for(let i=0;i<length;i++){
    const begin=Math.floor(i*rate/target),end=Math.min(pcm.length,Math.max(begin+1,Math.floor((i+1)*rate/target)));
    let value=0;for(let j=begin;j<end;j++) value+=pcm[j];
    value=Math.max(-1,Math.min(1,value/(end-begin)));
    view.setInt16(44+i*2,value<0?value*32768:value*32767,true);
  }
  return new Blob([buffer],{type:'audio/wav'});
}
async function sendAudio(blob,name,language){
  if(!ready || !$('consent').checked) throw new Error('CPU-Nachweis und Bestätigung erforderlich.');
  return teeClient.send(blob,language);
}

function append(text){
  if(!text.trim()) return;
  transcript.value+=(transcript.value.trim()?' ':'')+text.trim();transcript.scrollTop=transcript.scrollHeight;controls();
}
async function drain(){
  if(processing) return;
  processing=true;controls();
  try{
    while(queue.length){
      $('processing').textContent='Audio wird transkribiert …';
      const result=await sendAudio(queue[0],'live.wav',lastLanguage);
      queue.shift();completed++;append(result.text);
      status(recording?'Aufnahme läuft. Der nächste Textabschnitt folgt.':'Aufnahme beendet. Verbleibende Abschnitte werden verarbeitet.');
    }
    $('processing').textContent=`${completed} Audioabschnitte verarbeitet`;
    if(!recording && !stopping) status('Transkript bereit. Du kannst den Text bearbeiten und speichern.');
  }catch(error){
    // Keep the failed chunk for explicit retry instead of silently losing audio.
    if(recording) await stop();
    $('processing').textContent='Übertragung unterbrochen';
    status(`${error.message} ${queue.length} Abschnitt(e) warten. Fordere einen neuen CPU-Nachweis an und bestätige erneut, um sie zu senden.`,true);
  }finally{processing=false;controls();}
}
function enqueue(final=false){
  if(!samples || (!final && samples<context.sampleRate*8)) return;
  const pcm=merge(chunks,samples);chunks=[];samples=0;queue.push(wav(pcm,context.sampleRate));void drain();
  if(queue.length>=4 && recording){status('Die Transkription kommt nicht hinterher. Die Aufnahme wird beendet.',true);void stop();}
}
async function start(){
  if(!ready || !$('consent').checked || starting || processing || queue.length) return;
  if(!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode){
    status('Für das Mikrofon benötigst du einen aktuellen Browser und localhost oder HTTPS. Audio-Upload ist weiterhin möglich.',true);return;
  }
  starting=true;controls();
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    context=new AudioContext({sampleRate:16000});await context.audioWorklet.addModule('/static/pcm-worklet.js');await context.resume();
    chunks=[];samples=0;completed=0;lastLanguage=$('language').value;
    source=context.createMediaStreamSource(stream);capture=new AudioWorkletNode(context,'pcm-capture');
    silent=context.createGain();silent.gain.value=0;
    capture.port.onmessage=({data})=>{
      if(data==='flushed'){if(flushDone) flushDone();return;}
      if(!recording && !stopping) return;
      chunks.push(data);samples+=data.length;
      let energy=0;for(const sample of data) energy+=sample*sample;
      const level=Math.min(1,Math.sqrt(energy/data.length)*5);
      [...$('level').children].forEach((bar,i)=>{bar.style.height=`${5+level*(12+8*Math.sin(i*.8))}px`;});
      if(recording) enqueue();
    };
    source.connect(capture);capture.connect(silent);silent.connect(context.destination);
    recording=true;started=Date.now();$('level').classList.add('active');
    $('record').classList.add('recording');$('record-label').textContent='Aufnahme beenden';
    status('Aufnahme läuft. Der erste Textabschnitt erscheint nach etwa 8 Sekunden.');
    timer=setInterval(()=>{
      const seconds=Math.floor((Date.now()-started)/1000);
      $('timer').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
      if(seconds>=1800) void stop();
    },1000);
  }catch(error){
    stream?.getTracks().forEach(track=>track.stop());if(context && context.state!=='closed') await context.close();
    status(error.name==='NotAllowedError'?'Mikrofonzugriff wurde nicht erlaubt. Erlaube ihn im Browser oder öffne eine Audiodatei.':'Das Mikrofon konnte nicht gestartet werden. Prüfe das Eingabegerät.',true);
  }finally{starting=false;controls();}
}
async function stop(){
  if(!recording || stopping) return;
  stopping=true;recording=false;clearInterval(timer);controls();
  try{
    source.disconnect();stream.getTracks().forEach(track=>track.stop());
    await new Promise(resolve=>{
      const timeout=setTimeout(resolve,1000);flushDone=()=>{clearTimeout(timeout);resolve();};capture.port.postMessage('flush');
    });
    flushDone=undefined;enqueue(true);await context.close();
  }finally{
    stopping=false;$('level').classList.remove('active');[...$('level').children].forEach(bar=>bar.style.height='5px');
    $('record').classList.remove('recording');$('record-label').textContent='Aufnahme starten';
    status(queue.length?'Aufnahme beendet. Verbleibende Abschnitte werden verarbeitet.':'Aufnahme beendet. Dein Transkript ist bereit.');controls();
  }
}
$('record').addEventListener('click',()=>recording?void stop():void start());
$('consent').addEventListener('change',()=>{controls();if(ready && $('consent').checked && queue.length && !processing) void drain();status($('consent').checked?'Bereit. Starte eine Aufnahme oder öffne eine Audiodatei.':'Bestätige die GPU-Verarbeitung nach dem CPU-Nachweis, um zu beginnen.');});
$('check').addEventListener('click',()=>void check());
$('report-download').addEventListener('click',()=>{
  if(!attestationReport) return;
  const {amd_report,...verification}=attestationReport;
  const url=URL.createObjectURL(new Blob([JSON.stringify({...amd_report,gpu_attestation:attestationReport.gpu_attestation,verification},null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='cpu-attestation-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('audio-file').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file) return;
  if(!ready || !$('consent').checked || processing || recording) return;
  if(!file.size || file.size>64*1024*1024){status('Wähle eine Audiodatei zwischen 1 Byte und 64 MB.',true);event.target.value='';return;}
  processing=true;controls();status('Deine Aufnahme wird transkribiert …');$('processing').textContent='Datei wird transkribiert …';
  try{
    const result=await sendAudio(file,file.name,$('language').value);append(result.text);
    status(result.text?'Transkript bereit. Du kannst den Text bearbeiten und speichern.':'In dieser Aufnahme wurde keine Sprache erkannt.');
    $('processing').textContent=`Verarbeitet in ${result.processing_seconds.toFixed(1)} Sekunden`;
  }catch(error){status(error.message+' Wähle die Datei erneut, um es noch einmal zu versuchen.',true);$('processing').textContent='Datei nicht verarbeitet';}
  finally{processing=false;event.target.value='';controls();}
});
transcript.addEventListener('input',controls);
$('clear').addEventListener('click',()=>{transcript.value='';completed=0;$('timer').textContent='00:00';$('processing').textContent='Bereit für deine Stimme';controls();});
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(transcript.value);status('Transkript kopiert.');}catch{status('Kopieren nicht möglich. Markiere den Text und kopiere ihn mit der Tastatur.',true);}});
$('download').addEventListener('click',()=>{
  const url=URL.createObjectURL(new Blob([transcript.value],{type:'text/plain;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`transkript-${new Date().toISOString().slice(0,10)}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('pagehide',()=>{stream?.getTracks().forEach(track=>track.stop());});
void check();
