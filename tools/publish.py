#!/usr/bin/env python3
"""Push unchanged OCI digests and attach reviewable verification artifacts."""
import base64, hashlib, json, os, re, subprocess, urllib.request
from pathlib import Path
from policy import generate

ROOT=Path(__file__).resolve().parent.parent
REPO='kiz-speeches/whisper-confidential'

def github(path, token, data=None, content_type='application/json', method=None):
    url=path if path.startswith('https://') else 'https://api.github.com/repos/'+REPO+'/'+path
    if isinstance(data,dict):data=json.dumps(data).encode()
    request=urllib.request.Request(url,data=data,headers={'Authorization':'Bearer '+token,
        'Accept':'application/vnd.github+json','Content-Type':content_type,
        'X-GitHub-Api-Version':'2022-11-28'},method=method)
    with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)

def main():
    token=os.environ['GITHUB_TOKEN']
    manifest_path=ROOT/'.build/dist/release-manifest.json';manifest=json.loads(manifest_path.read_text())
    version=manifest['version']
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',version):
        raise ValueError('Invalid release version')
    authdir=ROOT/'.build/registry-auth';authdir.mkdir(mode=0o700,exist_ok=True)
    authfile=authdir/'config.json'
    prefix=manifest['build_inputs']['registry_prefix'];registry=prefix.split('/',1)[0]
    if registry=='ghcr.io':
        entry={'auth':base64.b64encode((os.environ['GITHUB_ACTOR']+':'+token).encode()).decode()}
    else:
        original=Path(os.environ.get('DOCKER_CONFIG', str(Path.home()/'.docker')))/'config.json'
        entries=json.loads(original.read_text())['auths']
        entry=entries.get(registry) or entries.get('https://'+registry)
        if not entry:raise ValueError('Runner has no credentials for configured registry')
    authfile.write_text(json.dumps({'auths':{registry:entry}}))
    authfile.chmod(0o600)
    tool=manifest['build_inputs']['registry_copy_image']
    try:
        for component,key in (('cpu','cpu_gateway'),('gpu','gpu_worker')):
            name=prefix+'-'+component
            command=['docker','run','--rm','--network','host','-v',str(authfile)+':/auth.json:ro',
                '-v',str(ROOT/'.build/dist')+':/images:ro',tool]
            subprocess.run(command+['copy','--authfile','/auth.json','--all','--preserve-digests',
                'oci-archive:/images/build-1/'+component+'.oci.tar','docker://'+name+':'+version],check=True)
            digest=manifest['images'][key]['platform_digest']
            raw=subprocess.check_output(command+['inspect','--authfile','/auth.json','--raw',
                                       'docker://'+name+'@'+digest])
            if hashlib.sha256(raw).hexdigest()!=digest[7:]:raise ValueError('Published OCI digest changed')
            manifest['images'][key]['registry_reference']=name+'@'+digest
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
        os.environ['DOCKER_CONFIG']=str(authdir)
        generate(manifest_path, ROOT/'.build/dist')
    finally:
        authfile.unlink(missing_ok=True)
    dist=ROOT/'.build/dist'
    files=[manifest_path,dist/'policy.rego',dist/'initdata.toml',dist/'attestation-policy.json',
           dist/'policy-input.json',dist/'policy-settings.json']
    sums=dist/'SHA256SUMS';sums.write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    release=publish_release(token,manifest,files+[sums])
    print('Published private prerelease:',release['html_url'])

def publish_release(token, manifest, files):
    version=manifest['version']
    release=github('releases',token,{'tag_name':version,'target_commitish':manifest['git_commit'],
        'name':version,'draft':True,'prerelease':True,'body':
        'Images are pinned by digest in release-manifest.json. '
        'Rebuilds must match both OCI platform digests. policy.rego and initdata.toml bind the CPU '
        'image and launch configuration. Compare signed SNP HOST_DATA to attestation-policy.json '
        'obtained from this trusted release. GPU processing is currently not confidential. '
        'Generation alone is not evidence of deployment or successful hardware tests.'})
    for path in files:
        content=path.read_bytes()
        uploaded=github(release['upload_url'].split('{',1)[0]+'?name='+path.name,token,content,
                        'application/octet-stream')
        if (uploaded.get('state')!='uploaded' or uploaded.get('name')!=path.name
                or uploaded.get('size')!=len(content)
                or uploaded.get('digest')!='sha256:'+hashlib.sha256(content).hexdigest()):
            raise ValueError('Release asset upload verification failed: '+path.name)
    # Partial or failed uploads remain drafts; complete builds publish automatically.
    published=github('releases/'+str(release['id']),token,
                     {'draft':False,'prerelease':True,'make_latest':'false'},method='PATCH')
    if published.get('draft') is not False or published.get('prerelease') is not True:
        raise ValueError('Release publication was not confirmed')
    return published

if __name__=='__main__':main()
