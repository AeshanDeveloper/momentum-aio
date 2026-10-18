import os
import sys
import asyncio

# Ensure python/ directory is in path
python_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "python")
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from python.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
