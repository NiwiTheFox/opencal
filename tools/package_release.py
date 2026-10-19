"""Package only public app sources and the artificial example. No dependencies."""
import hashlib,json,zipfile,argparse
from pathlib import Path

DOCS={'ARCHITECTURE.md','FORMATS.md','RELEASE-NOTES.md','SOURCE-REVIEW.md','ROADMAP.md'}
ROOT_FILES={'README.md','CHANGELOG.md','NOTICE','LICENSE','LICENSE-MIT-0.1','OpenCal.exe','Launch.cmd','.gitignore'}


def public_files(root):
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(root)
        if any(part in ('__pycache__','.git') for part in rel.parts):continue
        if path.suffix in ('.pyc','.pyo'):continue
        if rel.parts[0]=='docs' and rel.name not in DOCS:continue
        if len(rel.parts)==1 and rel.name not in ROOT_FILES:continue
        if len(rel.parts)>1 and rel.parts[0] not in ('opencal','tests','third_party','tools','examples','docs','.github'):continue
        if path.is_symlink() or path.name.endswith('.audit.json') or path.suffix.lower() in ('.ocproj','.ori') or path.suffix.lower()=='.bin' and rel.as_posix()!='examples/synthetic.bin':
            raise ValueError('Unexpected private binary/project in public sources: '+rel.as_posix())
        data=path.read_bytes()
        if rel.as_posix()=='opencal/data/reference-profiles.json':
            data=json.dumps({'schema':'opencal.reference-catalog','version':1,'profiles':[]},indent=2).encode()
        yield rel.as_posix(),data


def package(root,output,version):
    files=list(public_files(root));manifest={name:hashlib.sha256(data).hexdigest() for name,data in files}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files:archive.writestr(f'OpenCal-{version}/{name}',data)
        archive.writestr(f'OpenCal-{version}/SOURCE-MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP integrity failed.')
    sha=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(f'{sha}  {output.name}\n')
    return len(files),sha


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    print(package(root,Path(args.output),args.version))
