"""Build an app-local Windows CPython/Tcl/Tk distribution, without pip packages.

Runtime binaries/scripts are copied unchanged from the build interpreter. Only
path configuration is added. Developer files, caches and site-packages are omitted.
License downloads use official CPython/Tcl/Tk sources and fail on any TLS error.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path
import tkinter
from tools.package_release import public_files


def copy_runtime(python_root,target):
    target.mkdir(parents=True,exist_ok=False)
    version=f'{sys.version_info.major}{sys.version_info.minor}'
    required=['python.exe','pythonw.exe','python3.dll',f'python{version}.dll','LICENSE.txt']
    required += [p.name for p in python_root.glob('vcruntime*.dll')]
    for name in required:shutil.copy2(python_root/name,target/name)
    def ignored(directory,names):
        return [name for name in names if name in ('__pycache__','site-packages','test','tests','idlelib','turtledemo','ensurepip') or
                name.endswith(('.pyc','.pdb','.lib','.exp','.sh','.ico','.cat')) or '_d.' in name or f'cp{version}t' in name]
    for name in ('Lib','DLLs','tcl'):shutil.copytree(python_root/name,target/name,ignore=ignored)
    # A DLL-named _pth file overrides registry, environment and user site paths.
    (target/f'python{version}._pth').write_text('.\nDLLs\nLib\n..\n',encoding='utf-8')


def licenses(root,target):
    target.mkdir()
    py='.'.join(map(str,sys.version_info[:3]));tcl=tkinter.Tcl().call('info','patchlevel')
    if not re.fullmatch(r'\d+\.\d+\.\d+',tcl):raise ValueError('Unsupported Tcl version string.')
    urls={
        'Python-components.html':f'https://docs.python.org/release/{py}/license.html',
        'Tcl-LICENSE.txt':f'https://raw.githubusercontent.com/tcltk/tcl/core-{tcl.replace(".","-")}/license.terms',
        'Tk-LICENSE.txt':f'https://raw.githubusercontent.com/tcltk/tk/core-{tcl.replace(".","-")}/license.terms'}
    shutil.copy2(root/'LICENSE.txt',target/'Python-LICENSE.txt')
    for name,url in urls.items():
        with urllib.request.urlopen(url,timeout=60) as response:data=response.read()
        if len(data)<500:raise ValueError('License download is incomplete: '+name)
        (target/name).write_bytes(data)
    return {'python':py,'tcl':tcl,'license_sources':urls,
            'packaging_changes':'Runtime files unchanged; development files/site-packages omitted; isolated _pth added.'}


def build(source,target,archive,version):
    if sys.platform!='win32' or sys.maxsize<2**32:raise ValueError('Build with 64-bit Windows CPython.')
    if target.exists() or archive.exists():raise ValueError('Use a new output directory and archive; existing builds are preserved.')
    target.mkdir(parents=True)
    for name,data in public_files(source):
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    python_root=Path(sys.base_prefix);copy_runtime(python_root,target/'runtime')
    meta=licenses(python_root,target/'runtime-licenses')
    probe='import sys,tkinter,opencal,json; r=tkinter.Tk(); r.withdraw(); print(json.dumps({"executable":sys.executable,"isolated":sys.flags.isolated,"tcl":r.tk.call("info","library"),"tk":r.tk.eval("set tk_library"),"version":opencal.__version__})); r.destroy()'
    # Deliberately unusable external Python configuration tests isolation.
    env=dict(os.environ,PYTHONHOME='Z:/missing-python',PYTHONPATH='Z:/missing-modules')
    env.pop('TCL_LIBRARY',None);env.pop('TK_LIBRARY',None)
    result=subprocess.run([str((target/'runtime/python.exe').resolve()),'-c',probe],cwd=target.parent,env=env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Bundled interpreter/Tk startup failed:\n'+result.stderr)
    evidence=json.loads(result.stdout)
    for key in ('executable','tcl','tk'):
        if not Path(evidence[key]).resolve().is_relative_to(target.resolve()):raise ValueError('Runtime escaped bundle: '+key)
    if not evidence['isolated']:raise ValueError('Runtime is not isolated.')
    meta['probe']=evidence
    # The report uses paths relative to the bundle, not build-host locations.
    for key in ('executable','tcl','tk'):meta['probe'][key]=str(Path(evidence[key]).relative_to(target.resolve()))
    (target/'RUNTIME-MANIFEST.json').write_text(json.dumps(meta,indent=2))
    manifest={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(target.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    (target/'BUNDLE-MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for name in [*manifest,'BUNDLE-MANIFEST.json']:
            output.write(target/name,f'OpenCal-{version}-Windows/'+name)
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:raise ValueError('Portable ZIP integrity failed.')
    sha=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_suffix(archive.suffix+'.sha256').write_text(f'{sha}  {archive.name}\n')
    return {'files':len(manifest),'zip_bytes':archive.stat().st_size,'sha256':sha,'runtime':meta}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);parser.add_argument('--directory',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[1],Path(args.directory).resolve(),Path(args.output).resolve(),args.version),indent=2))
