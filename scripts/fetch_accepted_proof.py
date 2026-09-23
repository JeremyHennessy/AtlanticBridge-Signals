"""Read exact pinned proof bytes, falling back to an unpublished retained copy."""
import argparse
import os
from pathlib import Path
from archive_evidence import Client, accepted_proof

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-id',type=int,required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();path=Path(args.output)
    if path.exists():raise ValueError('Refusing to overwrite an existing proof file')
    _,raw=accepted_proof(Client(os.environ.get('GH_TOKEN','')),args.artifact_id)
    with path.open('xb') as output:output.write(raw)
if __name__=='__main__':main()
