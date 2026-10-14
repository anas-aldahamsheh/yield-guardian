"""Statistics and provenance helpers shared by the Yield Guardian training pipelines.

Modules:

- ``estimates``: point estimates with confidence intervals in the artifact contract format.
- ``bootstrap``: stratified, paired and cluster bootstrap with percentile intervals.
- ``metrics``: ranking, calibration and fixed false-positive-rate metrics.
- ``multiple_testing``: Benjamini-Hochberg false discovery rate control.
- ``provenance``: SHA-256 digests, git commit, package versions, seed derivation.
- ``io``: deterministic JSON and NPZ writers.
"""

__version__ = "0.1.0"
