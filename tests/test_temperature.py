import json

from src.agents.temperature import TemperatureSweepConfig, sweep_temperatures, write_temperature_report
from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.utils.data_loader import build_panel


class TemperatureClient:
    def __init__(self, temperature: float, repeat: int):
        self.temperature = temperature
        self.repeat = repeat

    def generation_params(self):
        return {"temperature": self.temperature, "repeat": self.repeat, "backend": "test"}

    def generate(self, prompt, system=None):
        del prompt, system
        if self.temperature == 0.0:
            expression = "rank(eps)"
        elif self.temperature == 0.5:
            field = "operating_cash_flow" if self.repeat == 0 else "total_assets"
            expression = f"rank(delta({field}, 1))"
        else:
            expression = "rank(unknown_field)"
        return json.dumps(
            [
                {
                    "name": f"candidate_{self.temperature}_{self.repeat}",
                    "expression": expression,
                    "economic_rationale": "controlled test",
                    "fields_used": (
                        ["unknown_field"]
                        if self.temperature == 1.0
                        else (["eps"] if self.temperature == 0.0 else ["operating_cash_flow" if self.repeat == 0 else "total_assets"])
                    ),
                }
            ]
        )


def test_temperature_sweep_reports_validity_novelty_and_pareto(tmp_path):
    cfg = Config(start_date="2020-01-01", end_date="2020-06-30", train_end="2020-03-31")
    panel = build_panel(cfg, save=False)
    report = sweep_temperatures(
        existing_factors=list(BASELINE_FACTORS),
        generation_context={"field_catalog": []},
        field_dict=set(panel.columns),
        panel=panel,
        client_factory=lambda temperature, repeat: TemperatureClient(temperature, repeat),
        config=TemperatureSweepConfig((0.0, 0.5, 1.0), repeats=2, candidates_per_repeat=1),
    )

    rows = {row["temperature"]: row for row in report["rows"]}
    assert rows[0.0]["validity_rate"] == 1.0
    assert rows[0.0]["novelty_rate"] == 0.0
    assert rows[0.5]["validity_rate"] == 1.0
    assert rows[0.5]["novelty_rate"] == 0.5
    assert rows[0.5]["accepted_after_novelty_count"] == 2
    assert rows[0.5]["pareto_optimal"] is True
    assert rows[1.0]["validity_rate"] == 0.0
    assert rows[1.0]["pareto_optimal"] is False

    output = write_temperature_report(report, tmp_path)
    assert (output / "temperature_sweep.json").exists()
    assert (output / "temperature_sweep.csv").exists()


def test_temperature_sweep_rejects_non_positive_sample_counts():
    cfg = Config(start_date="2020-01-01", end_date="2020-02-01", train_end="2020-01-15")
    panel = build_panel(cfg, save=False)

    try:
        sweep_temperatures(
            existing_factors=[],
            generation_context={},
            field_dict=set(panel.columns),
            panel=panel,
            client_factory=lambda temperature, repeat: TemperatureClient(temperature, repeat),
            config=TemperatureSweepConfig((0.5,), repeats=0, candidates_per_repeat=1),
        )
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected invalid sweep config to fail")
