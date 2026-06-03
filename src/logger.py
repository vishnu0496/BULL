import logging
from logging.handlers import RotatingFileHandler
import os

# Create logs directory if it doesn't exist at the root of the project
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "system.log")

def get_logger(name):
    logger = logging.getLogger(name)
    
    # If logger already has handlers, don't add them again
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)
    
    # Format: [TIMESTAMP] [LEVEL] [MODULE] - MESSAGE
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] - %(message)s')
    
    # RotatingFileHandler
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Default logger
logger = get_logger(__name__)
