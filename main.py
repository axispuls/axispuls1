import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if __name__ == "__main__":
    if "--worker" in sys.argv:
        from service_worker import run_service_loop
        run_service_loop()
    else:
        from gui_app import main
        main()
