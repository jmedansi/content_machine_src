import os
import sys
import time
import logging

ROOT = os.path.abspath(os.path.dirname(__file__))
# Ensure project folders are on sys.path (same logic as webhook_server.py)
PROJ_ROOT = os.path.dirname(ROOT)
sys.path.insert(0, PROJ_ROOT)
sys.path.insert(0, os.path.join(PROJ_ROOT, "dashboard"))
sys.path.insert(0, os.path.join(PROJ_ROOT, "gateway"))
sys.path.insert(0, ROOT)
LOG_FILE = r"D:\hub_telegram\content_gateway_service.log"
PID_FILE = r"D:\hub_telegram\content_gateway.pid"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

def write_pid():
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write pid file: {e}")

def remove_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception as e:
        logging.error(f"Failed to remove pid file: {e}")

def main():
    write_pid()
    from webhook_monitor.agent import app
    import uvicorn

    while True:
        try:
            logging.info("Starting uvicorn for webhook_monitor.agent:app on port 8000")
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
            logging.warning("uvicorn.run exited normally — restarting in 5s")
        except Exception:
            logging.exception("Exception in uvicorn — will restart in 5s")
        time.sleep(5)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        remove_pid()
