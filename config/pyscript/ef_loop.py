# v0.3.4 20240902 1650 adding more puzzle items 2

#same imports as set_ef.py
import sys
import json
import requests
import hashlib
import hmac
import random
import time
import binascii
from urllib.parse import urlencode
#gue
from datetime import datetime
import math

def get_map(json_obj, prefix=""):
    def flatten(obj, pre=""):
        result = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                result.update(flatten(v, f"{pre}.{k}" if pre else k))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                result.update(flatten(item, f"{pre}[{i}]"))
        else: result[pre] = obj
        return result
    return flatten(json_obj, prefix)

def get_qstr(params): return '&'.join([f"{key}={params[key]}" for key in sorted(params.keys())])

def hmac_sha256(data, key):
    hashed = hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).digest()
    sign = binascii.hexlify(hashed).decode('utf-8')
    return sign

def rest_api(method, url, key, secret, params=None): #rest method parameterized
    nonce     = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers   = {'accessKey':key,'nonce':nonce,'timestamp':timestamp}
    sign_str  = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    if method == "put": response = task.executor(requests.put, url, headers=headers, json=params)
    elif method == "get": response = task.executor(requests.get, url, headers=headers, json=params)
    else: response = task.executor(requests.post, url, headers=headers, json=params) #"post"
    if response.status_code == 200: return response.json()
    else: log.warning(f"rest {method}: {response.text}")

def check_if_device_is_online(SN=None, payload=None):
    parsed_data = payload
    desired_device_sn = SN
    device_found = False
    for device in parsed_data.get('data', []):
        if device.get('sn') == desired_device_sn:
            device_found = True
            if device.get('online', 0) == 1: return "online"
            else: return "offline"
    if not device_found: return "device not found"

#get_val of entity (generalized) via official api
def get_val(quotas, url, key, secret, Snr):
    params = {"quotas": quotas}
    #log.warning(f"params {params}")
    payload = post_api(url, key, secret, {"sn":Snr,"params":params})
    #log.warning(f"payload.status_code {payload.status_code}")
    if payload.status_code == 200:
        try:
            d = payload.json()['data'][quotas[0]] #[0]!
            #log.warning(f"d {d}")
            return d
        except KeyError as e:
            log.warning(f"Error accessing {quotas[0]} in payload")
            return 0
    else:
        log.warning(f"payload.status_code {quotas[0]} not 200")
        return 0

##get_device_name from Snr when used instead of Snr

# def set_ef_loop(value):
#     service.call("input_number", "set_value", entity_id="input_number.ef_loop", value=value)
def set_ef_loop(hass, value=None): #Copilot suggestion NOGO
    hass.services.call("input_select", "select_option", {"entity_id": "input_select.ef_loop", "option": value})

def set_inv_out_manual(value):
    service.call("input_number", "set_value", entity_id="input_number.inv_out_manual", value=value)

def set_morning(value, value2):
    if value: service.call("input_boolean", "turn_on", entity_id="input_boolean.morning")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.morning")
    if value2: service.call("input_boolean", "turn_on", entity_id="input_boolean.ran_today")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.ran_today")

@service
def ef_loop(EcoflowKey=None, EcoflowSecret=None, PsSnr=None, DeltaSnr=None, ShrdzmSnr=None):
    if PsSnr is None: #PsName, DeltaName not necessary any more
        log.warning(f"PsSnr=None, exiting") 
        return #instead: input_boolean.ef_loop = "off"
    url = 'https://api-e.ecoflow.com/iot-open/sign/device/quota' #api-e. instead of api. according to Günther Nid FB
    #use <method> arg v <method>_api(), str v url_const, EcoflowKey v key & EcoflowSecret v secret
    payload = rest_api('get','https://api-e.ecoflow.com/iot-open/sign/device/list',EcoflowKey,EcoflowSecret,{"sn":PsSnr})
    log.warning(f"payload {payload}") #online devices json: PS & Delta
    #instead of assigning unused check_ps_status
    #if not check_if_device_is_online(PsSnr, payload) == "online"
    #log.warning(f"{check_if_device_is_online(PsSnr, payload)}")
    #set_ef_loop(hass, "off") #hangs ha!?

    i = 1
    while state.get("input_boolean.ef_loop") == "on":
        #log.warning(f"i {i}")
        if i < 60:
            i += 1
        else:
            i = 1 #1st sec of 1 minute loop
        task.sleep(1)
