import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def pytest_addoption(parser):
    parser.addoption('--hermes-source', help='Verified v0.23.1 source cache for source-level regression tests')
