import ast
from seed.seed import Plant


def test_real_growth_hot_execution_and_restore(plant):
    root = plant.tree.root
    before = (root / 'seed.py').stat().st_size
    a = plant.grow()
    b = plant.grow('filter', inline=False)
    c = plant.grow('oscillator', inline=False)
    assert a and b and c
    assert (root / 'seed.py').stat().st_size > before
    assert len(list(root.rglob('*.py'))) == 3
    for file in root.rglob('*.py'):
        ast.parse(file.read_text())
    plant.render()
    assert plant.counters['calls'] == 3
    assert all(n.activity > 0 for n in plant.nodes.values())
    plant.close()
    restored = Plant(root, root.parent / 'environment.json', genome=plant.genome)
    try:
        assert set(restored.nodes) == {a, b, c}
        assert restored.render().any()
    finally:
        restored.close()


def test_dormancy_and_autonomous_germination(plant):
    plant.energy = 3.0
    env = plant.environment
    env.write_text('{"nutrients": 0}')
    for _ in range(20):
        plant.step()
    assert not plant.nodes
    env.write_text('{"nutrients": 8}')
    for _ in range(40):
        plant.step()
        plant.render()
    assert plant.nodes


def test_fixed_rng_reproduces_nested_growth_mutation_and_pruning(tmp_path):
    from dataclasses import replace
    from scripts.prepare_lab import prepare
    from seed.seed import Genome
    import numpy as np

    def experiment(name):
        root = prepare(tmp_path / name / 'laboratory')
        p = Plant(root, root.parent / 'environment.json', rng_seed=17,
                  genome=replace(Genome(), write_interval=0))
        try:
            for i in range(12):
                p.energy = 24
                p.grow(['oscillator', 'filter', 'resonator', 'pulser'][i % 4], inline=(i == 0))
                p.render()
            assert any(len(n.path.split('/')) > 3 for n in p.nodes.values())
            for identifier in list(p.nodes)[:4]:
                p.energy = 24
                assert p.mutate(identifier, structural=True)
            victim = list(p.nodes)[2]
            p.mark_dying(victim)
            p.age += p.genome.decay_seconds
            assert p.prune(victim)
            output = p.render()
            return [(n.id, n.path, n.parents, n.source) for n in p.nodes.values()], output
        finally:
            p.close()
    first, a = experiment('a')
    second, b = experiment('b')
    assert first == second
    assert np.array_equal(a, b)
