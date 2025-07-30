import logging
import sys
from fastapi.logger import logger
    
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
#dictConfig(log_config)
logger = logging.getLogger(__name__)
    
def get_logger(name):
    return logger