from src.config import CONFIG


def test_config_importable_and_dirs_exist():
    assert CONFIG.freq == "D"
    assert CONFIG.data_dir.exists()
    assert CONFIG.results_dir.exists()
