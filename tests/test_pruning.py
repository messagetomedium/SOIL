import numpy as np


def test_pruning_erases_inline_code_files_and_active_functions(plant):
    a = plant.grow()
    b = plant.grow('filter', inline=False)
    path = plant.nodes[b].path
    plant.render()
    plant.mark_dying(b)
    assert plant.nodes[b].state == 'dying'
    assert not plant.prune(b)
    plant.age += plant.genome.decay_seconds
    assert plant.prune(b)
    assert b not in plant.nodes
    assert not (plant.tree.root / path).exists()
    assert not (plant.tree.root / path).parent.exists()
    calls = plant.counters['calls']
    plant.render()
    assert plant.counters['calls'] == calls + 1
    plant.mark_dying(a)
    plant.age += plant.genome.decay_seconds
    assert plant.prune(a)
    assert 'def tissue_' + a not in plant.tree.read('seed.py')
    assert not plant.nodes
    for _ in range(30):
        silence = plant.render()
    assert np.max(abs(silence)) < 1e-8
    assert (plant.tree.root / 'seed.py').exists()
    assert plant.tree.root.exists()


def test_starvation_autonomously_removes_tissue(plant):
    plant.grow()
    plant.grow('oscillator', inline=False)
    plant.energy = 0.1
    plant.environment.write_text('{"nutrients": 0}')
    before = sum(len(plant.tree.read(p)) for p in plant.tree.sources())
    for _ in range(16):
        plant.step()
        plant.render()
    after = sum(len(plant.tree.read(p)) for p in plant.tree.sources())
    assert plant.counters['pruned'] == 2
    assert after < before
