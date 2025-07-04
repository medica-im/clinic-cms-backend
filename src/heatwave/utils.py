import logging
from django.conf import settings
import requests

logger=logging.getLogger(__name__)

url="https://public-api.meteofrance.fr/public/DPVigilance/v1/textesvigilance/encours"
headers = {
    'accept': '*/*',
    'apikey': settings.PUBLIC_API_METEOFRANCE
}
def get_warning():
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        logger.debug(f"{data=}")
    else:
        # Print an error message
        logger.error(f'Error fetching data: {response.status_code=}')