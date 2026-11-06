import numpy as np
from seed.seed import AudioOutput


def test_growth_changes_sound_and_bounds_output(plant):
    a = plant.grow()
    first = plant.render(4096)
    assert np.sqrt(np.mean(first * first)) > 0.001
    plant.grow('pulser', inline=False)
    plant.sample_index = 0
    changed = plant.render(4096)
    assert not np.allclose(first, changed)
    assert np.max(abs(changed)) <= 0.16
    assert np.isfinite(changed).all()
    assert np.max(abs(np.diff(changed))) <= 0.015001
    assert plant.nodes[a].memory == {}


def test_phase_continuity_and_dc_protection(plant):
    n = plant.grow()
    plant.transition = False
    f = plant.nodes[n].function
    t1 = np.arange(480) / plant.sample_rate
    t2 = np.arange(480, 960) / plant.sample_rate
    full = f(np.r_[t1, t2], np.zeros(960), {})
    split = np.r_[f(t1, np.zeros(480), {}), f(t2, np.zeros(480), {})]
    assert np.array_equal(full, split)
    plant.nodes[n].function = lambda t, x, z: np.full_like(t, 1.0)
    for _ in range(12):
        block = plant.render()
    assert np.max(abs(block)) < 1e-6


def test_nonfinite_tissue_and_callback_buffer(plant):
    n = plant.grow()
    plant.nodes[n].function = lambda t, x, z: np.full_like(t, np.nan)
    assert np.isfinite(plant.render()).all()
    audio = AudioOutput(24000, 480, enabled=False)
    output = np.empty((480, 1), dtype=np.float32)
    audio.callback(output, 480, None, False)
    assert not output.any()
    assert audio.underflows == 1
    block = np.full(480, 0.01, dtype=np.float32)
    audio.submit(block)
    audio.callback(output, 480, None, False)
    assert np.array_equal(output[:, 0], block)
    for _ in range(30):
        audio.submit(block)
    assert len(audio.queue) == 6
