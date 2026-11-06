from dataclasses import replace
import pytest
from scripts.prepare_lab import prepare
from seed.seed import Genome, Plant


@pytest.fixture
def plant(tmp_path):
    root = prepare(tmp_path / 'laboratory')
    p = Plant(root, root.parent / 'environment.json', rng_seed=17,
              genome=replace(Genome(), write_interval=0))
    p.energy = 24
    yield p
    p.close()
