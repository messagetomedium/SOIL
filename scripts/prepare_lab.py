#!/usr/bin/env python3
"""Place only an untouched seed and static resources; never grow tissue."""
import argparse
import json
from pathlib import Path
import shutil


def prepare(laboratory):
    laboratory = Path(laboratory).absolute()
    if laboratory != laboratory.resolve():
        raise ValueError('laboratory path must not contain symlinks')
    laboratory.mkdir(parents=True, exist_ok=True, mode=0o700)
    plant = laboratory / 'plant_001'
    if plant.is_symlink():
        raise ValueError('plant symlink rejected')
    plant.mkdir(exist_ok=True, mode=0o700)
    target = plant / 'seed.py'
    # Exclusive creation preserves a living plant on repeated setup.
    if not target.exists() and not target.is_symlink():
        with target.open('xb') as out:
            out.write((Path(__file__).resolve().parents[1] / 'seed' / 'seed.py').read_bytes())
    elif not target.is_file() or target.is_symlink():
        raise ValueError('seed must be a regular file')
    environment = laboratory / 'environment.json'
    if not environment.exists() and not environment.is_symlink():
        with environment.open('x') as out:
            json.dump({'nutrients': 1.7}, out, indent=2)
    elif not environment.is_file() or environment.is_symlink():
        raise ValueError('environment must be a regular file')
    return plant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--laboratory', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'laboratory')
    args = parser.parse_args()
    print(prepare(args.laboratory))


if __name__ == '__main__':
    main()
