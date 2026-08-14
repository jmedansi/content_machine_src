import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scheduler.log"

def get_node_logger(node_name: str) -> logging.Logger:
    """
    Creates a standardized logger for a specific node/agent.
    Writes INFO+ to file (UTF-8) and INFO to console.
    """
    logger = logging.getLogger(f"node.{node_name}")
    
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # File handler — INFO+ to logs/{node}.log
        LOG_FILE_NODE = LOG_DIR / f"{node_name}.log"
        fh = logging.FileHandler(LOG_FILE_NODE, encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        # Console handler — WARNING+ only (avoids noise on INFO, no emoji issues)
        import sys
        import io
        if sys.platform == "win32" and hasattr(sys.stderr, "buffer"):
            try:
                safe_stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
                ch = logging.StreamHandler(safe_stderr)
            except (ValueError, AttributeError):
                # Fallback if buffer is already closed or wrapped
                ch = logging.StreamHandler()
        else:
            ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
    
    return logger
