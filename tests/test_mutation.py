import numpy as np


def test_mutation_replaces_code_and_callable(plant):
    identifier = plant.grow('oscillator')
    before = plant.nodes[identifier]
    source_before = plant.tree.read('seed.py')
    t = np.arange(480) / plant.sample_rate
    expected = before.function(t, np.zeros(480), {})
    assert plant.mutate(identifier)
    after = plant.nodes[identifier]
    assert after.id == before.id
    assert after.revision == 1
    assert after.function is not before.function
    assert plant.tree.read('seed.py') != source_before
    assert not np.allclose(expected, after.function(t, np.zeros(480), {}))
    assert plant.genome.initial_frequency == 165.0


def test_structural_mutation_changes_executed_connections(plant):
    a = plant.grow('oscillator')
    b = plant.grow('oscillator', inline=False)
    c = plant.grow('filter', inline=False)
    plant.nodes[c].parents = [a]
    assert plant.mutate(c, structural=True)
    assert plant.nodes[c].parents == [a, b]
    plant.render()
    assert plant.nodes[c].activity > 0
