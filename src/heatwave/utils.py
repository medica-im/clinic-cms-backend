import logging
from django.conf import settings
from django.core.cache import cache
import requests
import json

logger=logging.getLogger(__name__)

url="https://public-api.meteofrance.fr/public/DPVigilance/v1/textesvigilance/encours"
url_carte="https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours"
headers = {
    'accept': '*/*',
    'apikey': settings.PUBLIC_API_METEOFRANCE
}
def _find_bloc_by_domain_id(data, domain_id: str) -> dict | None:
    for bloc in data.get("product", {}).get("text_bloc_items", []):
        if bloc.get("domain_id") == domain_id:
            return bloc
    return None

def get_warning_cached():
    return cache.get_or_set(
        "vigilance_cdp_textes",
        lambda: get_warning(),
        settings.PUBLIC_API_METEOFRANCE_TTL
    )

def get_warning():
    response = requests.get(url, headers=headers)
    logger.debug(f"Météo France API response status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        logger.debug(f"API returned {len(data.get('product', {}).get('text_bloc_items', []))} text_bloc_items")
        logger.debug(f"Full API response: {json.dumps(data, ensure_ascii=False)}")
        return data
    else:
        # Print an error message
        error_msg=f'Error fetching data: {response.status_code=}'
        logger.error(error_msg)
        raise Exception(error_msg)
    
def get_heatwave_by_department(dpt_code: str):
    res = {
        "start_time": None,
        "end_time": None,
        "risk_code": None
    }
    try:
        data=get_warning_cached()
    except Exception as e:
        raise Exception(e)

    logger.debug(f"{dpt_code=}")
    if data:
        bloc = _find_bloc_by_domain_id(data, dpt_code)
        if not bloc:
            logger.debug(f"No text_bloc_item found for {dpt_code=}")
            return res
        try:
            DEP_SUIVI__TEXT_ITEMS: list = bloc["bloc_items"][-1]["text_items"]
            logger.debug(f"{DEP_SUIVI__TEXT_ITEMS=}")
        except (KeyError, IndexError) as e:
            logger.debug(f"No text_items for {dpt_code=}: {e}")
            return res

        for text_item in DEP_SUIVI__TEXT_ITEMS:
            logger.debug(f"text_item hazard_code={text_item.get('hazard_code')}")
            if text_item["hazard_code"] == '6':
                term_item=text_item["term_items"][-1]
                logger.debug(f"{term_item=}")
                res["start_time"]=term_item["start_time"]
                res["end_time"]=term_item["end_time"]
                res["risk_code"]=term_item["risk_code"]
    logger.debug(f"get_heatwave_by_department result: {res}")
    return res


def get_carte_cached():
    return cache.get_or_set(
        "vigilance_carte",
        lambda: get_carte(),
        settings.PUBLIC_API_METEOFRANCE_TTL
    )

def get_carte():
    response = requests.get(url_carte, headers=headers)
    logger.debug(f"Météo France carte API response status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        logger.debug(f"Carte API response: {json.dumps(data, ensure_ascii=False)}")
        return data
    else:
        error_msg=f'Error fetching carte data: {response.status_code=}'
        logger.error(error_msg)
        raise Exception(error_msg)

def get_heatwave_by_department_carte(dpt_code: str):
    res = {
        "start_time": None,
        "end_time": None,
        "risk_code": None
    }
    try:
        data = get_carte_cached()
    except Exception as e:
        raise Exception(e)
    logger.debug(f"carte: {dpt_code=}")
    if not data:
        return res
    for period in data.get("product", {}).get("periods", []):
        for item in period.get("timelaps", {}).get("domain_ids", []):
            if item.get("domain_id") != dpt_code:
                continue
            for hazard in item.get("phenomenon_items", []):
                logger.debug(f"carte: {dpt_code=} hazard_id={hazard.get('phenomenon_id')} max_color_id={hazard.get('phenomenon_max_color_id')}")
                if str(hazard.get("phenomenon_id")) == "6":
                    color_id = hazard.get("phenomenon_max_color_id")
                    logger.debug(f"carte: CANICULE found {color_id=} timelaps_items={hazard.get('timelaps_items')}")
                    if color_id and color_id > 1:
                        timelaps_items = hazard.get("timelaps_items", [])
                        if timelaps_items:
                            last = timelaps_items[-1]
                            res["start_time"] = last.get("begin_time")
                            res["end_time"] = last.get("end_time")
                            res["risk_code"] = str(last.get("color_id", color_id))
                        else:
                            res["risk_code"] = str(color_id)
                        logger.debug(f"carte result: {res}")
                        return res
    logger.debug(f"carte result: {res}")
    return res

