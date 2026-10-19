"""Offline read-only analysis, suitable for repeatable integration checks."""
import argparse
import json
from pathlib import Path
from .core import read_binary,digest,differences,identify
from .checksums import inspect
from .edc15 import discover,dtc_records
from .multimap import inspect_multimap


def analyze(data):
    report={'sha256':digest(data),'size':len(data),'identity':identify(data,{}),
            'checksum':inspect(data),'multimap':inspect_multimap(data)}
    for key,fn in [('definitions',discover),('dtcs',dtc_records)]:
        try: report[key]=fn(data)
        except ValueError as exc: report[key]={'status':'unsupported','reason':str(exc)}
    return report


def main():
    parser=argparse.ArgumentParser(description='OpenCal read-only analysis; original files are never changed.')
    parser.add_argument('file'); parser.add_argument('--compare'); parser.add_argument('--report')
    args=parser.parse_args(); data=read_binary(args.file); report=analyze(data)
    if args.compare:
        other=read_binary(args.compare)
        report['comparison']={'other_sha256':digest(other),'other_size':len(other),'ranges':list(differences(data,other))}
    text=json.dumps(report,indent=2)
    if args.report:
        with Path(args.report).open('x',encoding='utf-8') as f: f.write(text)
    else: print(text)


if __name__=='__main__': main()
