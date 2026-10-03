"""Storage Visualizer: run this file to start the app.

    python storage_visualizer.py               pick a drive or folder in the app
    python storage_visualizer.py "D:\\Games"    start scanning that folder straight away
    python storage_visualizer.py --demo        try it on made-up data
"""

import sys

from storagevis.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
