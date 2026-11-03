import os
import sys
from pathlib import Path

os.environ["VILASA_MOCK"] = "1"  # tests never call the real API
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
