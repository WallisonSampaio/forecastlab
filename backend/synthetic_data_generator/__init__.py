"""Gerador de dados sintéticos do ForecastLab (reprodutível via ``random_seed``)."""

from .generator import GENERATOR_VERSION, SyntheticDataset, generate_dataset

__all__ = ["GENERATOR_VERSION", "SyntheticDataset", "generate_dataset"]
