from dataclasses import replace
import os
import pytest
from seed.seed import compile_tissue, Genome, Plant
from scripts.prepare_lab import prepare


@pytest.mark.parametrize('path', ['../outside.py', '/tmp/outside.py', 'branches/../../outside.py', './seed.py'])
def test_traversal_rejected(plant, path):
    with pytest.raises(ValueError):
        plant.tree.write(path, 'bad')
    with pytest.raises(ValueError):
        plant.tree.remove(path)


def test_symlink_hardlink_and_directory_escape(plant, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    victim = outside / 'victim.py'
    victim.write_text('untouched')
    root = plant.tree.root
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    (root / 'alias.py').symlink_to(victim)
    os.link(victim, root / 'hard.py')
    for path in ['escape/victim.py', 'alias.py', 'hard.py']:
        with pytest.raises((ValueError, OSError)):
            plant.tree.write(path, 'bad')
        with pytest.raises((ValueError, OSError)):
            plant.tree.remove(path)
    assert victim.read_text() == 'untouched'
    with pytest.raises(ValueError):
        plant.tree.sources()


@pytest.mark.parametrize('body', [
    '    import os\n    return x\n',
    "    return np.__dict__\n",
    "    return z.clear()\n",
    "    return __import__('os')\n",
    "    while True:\n        x = x\n    return x\n",
    "    np.sin = x\n    return x\n",
    "    def nested(t, x, z):\n        return x\n    return x\n",
])
def test_closed_code_grammar(body):
    with pytest.raises(ValueError):
        compile_tissue('def tissue_000000000001(t, x, z):\n' + body, '000000000001')


def test_failed_write_rolls_back_without_activating(plant, monkeypatch):
    original = plant.tree.read('seed.py')
    write = plant.tree.write
    def fail(name, text):
        if name == 'body.json':
            raise OSError('injected disk error')
        return write(name, text)
    monkeypatch.setattr(plant.tree, 'write', fail)
    with pytest.raises(OSError):
        plant.grow()
    assert not plant.nodes
    assert plant.tree.read('seed.py') == original


def test_limits_single_writer_and_idempotent_preparation(plant):
    with pytest.raises(BlockingIOError):
        Plant(plant.tree.root, plant.environment)
    plant.genome = replace(plant.genome, max_nodes=1)
    assert plant.grow()
    source = plant.tree.read('seed.py')
    assert not plant.grow()
    prepare(plant.tree.root.parent)
    assert source == plant.tree.read('seed.py')


def test_write_rate_limit_and_source_limit(plant):
    plant.genome = replace(Genome(), write_interval=1000)
    assert plant.grow()
    assert not plant.mutate()
    plant.genome = replace(plant.genome, write_interval=0, max_source_bytes=1)
    with pytest.raises(ValueError, match='byte budget'):
        plant.grow(inline=False)
