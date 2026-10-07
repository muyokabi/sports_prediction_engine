import logging.config
from pathlib import Path

import yaml

from sports_engine.core.paths import project_root


def configure_logging(config_path: Path | None = None, *, verbose: bool = False) -> None:
    path = config_path or project_root() / "config/logging.yaml"
    (project_root() / "logs").mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if verbose:
        config["root"]["level"] = "DEBUG"
        config["handlers"]["console"]["level"] = "DEBUG"
    logging.config.dictConfig(config)
