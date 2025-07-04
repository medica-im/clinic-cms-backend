import logging
from django.conf import settings
from django.core.cache import cache
import requests
import json

logger=logging.getLogger(__name__)

url="https://public-api.meteofrance.fr/public/DPVigilance/v1/textesvigilance/encours"
headers = {
    'accept': '*/*',
    'apikey': settings.PUBLIC_API_METEOFRANCE
}
domain_id_idx = {
    "FRA": 0,
    "ZDF_PARIS": 1,
    "ZDF_NORD": 2,
    "ZDF_SUD_OUEST": 3,
    "ZDF_SUD": 4,
    "ZDF_OUEST": 5,
    "ZDF_SUD_EST": 6,
    "ZDF_EST": 7,
    "10": 8,
    "11": 9,
    "12": 10,
    "13": 11,
    "14": 12,
    "15": 13,
    "16": 14,
    "17": 15,
    "18": 16,
    "19": 17,
    "21": 18,
    "22": 19,
    "23": 20,
    "24": 21,
    "25": 22,
    "26": 23,
    "27": 24,
    "28": 25,
    "29": 26,
    "30": 27,
    "31": 28,
    "32": 29,
    "33": 30,
    "34": 31,
    "35": 32,
    "36": 33,
    "37": 34,
    "38": 35,
    "39": 36,
    "40": 37,
    "41": 38,
    "42": 39,
    "43": 40,
    "43": 40,
    "44": 41,
    "45": 42,
    "46": 43,
    "47": 44,
    "48": 45,
    "49": 46,
    "50": 47,
    "51": 48,
    "52": 49,
    "53": 50,
    "54": 51,
    "55": 52,
    "56": 53,
    "57": 54,
    "58": 55,
    "59": 56,
    "60": 57,
    "61": 58,
    "62": 59,
    "63": 60,
    "64": 61,
    "65": 62,
    "66": 63,
    "67": 64,
    "68": 65,
    "69": 66,
    "70": 67,
    "71": 68,
    "72": 69,
    "73": 70,
    "74": 71,
    "02": 72,
    "03": 73,
    "04": 74,
    "75": 75,
    "76": 76,
    "77": 77,
    "78": 78,
    "79": 79,
    "80": 80,
    "81": 81,
    "82": 82,
    "83": 83,
    "84": 84,
    "85": 85,
    "86": 86,
    "87": 87,
    "88": 88,
    "89": 89,
    "90": 90,
    "91": 91,
    "05": 92,
    "06": 93,
    "07": 94,
    "08": 95,
    "09": 96,
    "2A": 97,
    "2B": 98,
    "92": 99,
    "93": 100,
    "94": 101,
    "95": 102,
    "99": 103,
    "01": 104
}

def get_warning_cached():
    return cache.get_or_set(
        "vigilance_cdp_textes",
        lambda: get_warning(),
        3600
    )

def get_warning():
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        logger.debug(f"{data=}")
        return data
    else:
        # Print an error message
        error_msg=f'Error fetching data: {response.status_code=}'
        logger.error(error_msg)
        raise Exception(error_msg)
    
def get_heatwave_by_department(dpt_code: str):
    res = {
        "start": None,
        "stop": None,
        "risk_code": None
    }
    try:
        data=get_warning_cached()
    except Exception as e:
        return 

    idx = domain_id_idx[dpt_code]

    try:
        test = data["product"]["text_bloc_items"][idx]
        test_json = json.dumps(test)
        return test_json
    except:
        return res
