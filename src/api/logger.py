import logging
import sys
from fastapi.logger import logger
    
# gunicorn logging settings
gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)
    
# create custom handler for INFO msg
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
    
logger.addHandler(stdout_handler)
    
def get_logger(name):
    return logger