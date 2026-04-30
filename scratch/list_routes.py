import sys
import os
sys.path.insert(0, os.path.abspath('hisabbot'))
from app.main import app

for route in app.routes:
    print(f"{route.methods} {route.path}")
