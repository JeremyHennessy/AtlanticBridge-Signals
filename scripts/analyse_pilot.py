"""Analyse private pilot records; no upload, storage mutation or invented enrollment."""
import argparse
import json
from pathlib import Path
from atlanticbridge.pilot_measurement import analyse

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input');ap.add_argument('--output');args=ap.parse_args()
    source=Path(args.input)
    if source.stat().st_size>2*1024*1024:raise ValueError('Pilot input exceeds 2 MB')
    result=analyse(json.loads(source.read_text()));text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.output:
        target=Path(args.output)
        if target.resolve()==source.resolve():raise ValueError('Do not overwrite the input evidence')
        if target.exists():raise ValueError('Output already exists; choose a new result path')
        target.write_text(text)
    else:print(text,end='')
if __name__=='__main__':main()
