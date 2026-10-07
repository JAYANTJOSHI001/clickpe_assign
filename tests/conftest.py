import os
import sys

# Ensure repository root is on the Python path during tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
