"""Benchmark result serialization."""
from dataclasses import asdict
import json
from pathlib import Path


def write_json(results, path):
    Path(path).write_text(json.dumps([asdict(item) for item in results], indent=2, sort_keys=True))
