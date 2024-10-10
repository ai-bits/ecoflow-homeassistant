# v0.3.11 20240924 2150 try in rest_api() to avoid exception
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
import traceback

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
    try:
        if method == "put": response = task.executor(requests.put, url, headers=headers, json=params)
        elif method == "get": response = task.executor(requests.get, url, headers=headers, json=params)
        elif method == "post": response = task.executor(requests.post, url, headers=headers, json=params)
        else: log.warning(f"rest_api method {method} not covered; only put get post")
        #log.warning(f"method {method}; response {response} .status_code {response.status_code} .json() {response.json()} .text=.json() w/o spaces")
    except Exception as e:
        log.warning(f"rest_api {method} exception {e}")
    if response.status_code == 200: return response if method == "post" else response.json()
    else: log.warning(f"rest_api {method} response.json() {response.json()}")

def device_online(SN=None, payload=None):
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
    payload = rest_api("post", url, key, secret, {"sn":Snr,"params":params})
    #log.warning(f"payload.status_code {payload}") 
    if payload.status_code == 200: #response <Response [200]> if method == "post" else response.json()
        try:
            tmp = payload.json()['data'][quotas[0]] #[0]!
            #log.warning(f"tmp {tmp}")
            return tmp
        except KeyError as e:
            pass #noop
            log.warning(f"Error accessing {quotas[0]} in payload")
            return 0
    else:
        log.warning(f"payload.status_code {quotas[0]} not 200")
        return 0

def set_ef_loop(value):
    if value: service.call("input_boolean", "turn_on", entity_id="input_boolean.ef_loop")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.ef_loop")

def set_inv_out_manual(value):
    service.call("input_number", "set_value", entity_id="input_number.inv_out_manual", value=value)

def set_morning(value, value2):
    if value: service.call("input_boolean", "turn_on", entity_id="input_boolean.morning")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.morning")
    if value2: service.call("input_boolean", "turn_on", entity_id="input_boolean.ran_today")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.ran_today")

#def 

@service
def ef_loop(EcoflowKey=None, EcoflowSecret=None, PsSnr=None, DeltaSnr=None, ShrdzmSnr=None):
    if PsSnr is None: #args camel-cased #PsName, DeltaName not necessary any more
        log.warning(f"PsSnr=None, exiting") 
        set_ef_loop(False)
    url = 'https://api-e.ecoflow.com/iot-open/sign/device/quota' #api-e. instead of api. according to Günther Nid FB
    #use <method> arg v <method>_api(), str v url_const, EcoflowKey v key & EcoflowSecret v secret
    payload = rest_api('get','https://api-e.ecoflow.com/iot-open/sign/device/list', EcoflowKey, EcoflowSecret, {"sn":PsSnr})
    #log.warning(f"rest_api get payload online devices json {payload}")
    if not device_online(PsSnr, payload) == "online":
        log.warning(f"PS offline")
        set_ef_loop(False)
    Morning = state.get('input_boolean.morning') == 'on'
    RanToday = state.get('input_boolean.ran_today') == 'on'
    if datetime.now().strftime('%H:%M') == state.get('sensor.sunrise_next_time'): #sunrise
        Morning = True
        RanToday = False
    input_number.battery_charge = get_val(["20_1.batSoc"], url, EcoflowKey, EcoflowSecret, PsSnr)
    if Morning and int(input_number.battery_charge) == 100:
        Morning = False
        RanToday = True
    set_morning(Morning, RanToday) #feed back Morning to morning and RanToday to ran_today

    sleep = 60
    while state.get("input_boolean.ef_loop") == "on":
        cur_perm_w = get_val(["20_1.permanentWatts"], url, EcoflowKey, EcoflowSecret, PsSnr)
        cur_perm_w = cur_perm_w if cur_perm_w == 0 else round(cur_perm_w / 10)
        input_number.battery_charge = get_val(["20_1.batSoc"], url, EcoflowKey, EcoflowSecret, PsSnr)
        #sensor.powerstream_1_battery_charge = input_number.battery_charge #for dash when EFC nogo
        state.set("sensor.powerstream_1_battery_charge", value=input_number.battery_charge)
        ##log.warning(f"sensor.powerstream_1_battery_charge {sensor.powerstream_1_battery_charge}")
        input_number.solar_1_watts = float(get_val(["20_1.pv1InputWatts"], url, EcoflowKey, EcoflowSecret, PsSnr) / 10)
        sensor.powerstream_1_solar_1_watts = input_number.solar_1_watts
        input_number.solar_2_watts = float(get_val(["20_1.pv2InputWatts"], url, EcoflowKey, EcoflowSecret, PsSnr) / 10)
        sensor.powerstream_1_solar_2_watts = input_number.solar_2_watts
        #log.warning(f"input_number.solar_1_watts {input_number.solar_1_watts}")
        #log.warning(f"input_number.solar_2_watts {input_number.solar_2_watts}")
        input_number.solar_1_in_power = float(get_val(["pd.pv1ChargeWatts"], url, EcoflowKey, EcoflowSecret, DeltaSnr))
        sensor.delta_2_max_2_solar_1_in_power = input_number.solar_1_in_power
        input_number.solar_2_in_power = float(get_val(["pd.pv2ChargeWatts"], url, EcoflowKey, EcoflowSecret, DeltaSnr))
        sensor.delta_2_max_2_solar_2_in_power = input_number.solar_2_in_power
        #log.warning(f"input_number.solar_1_in_power {input_number.solar_1_in_power}")
        #log.warning(f"input_number.solar_2_in_power {input_number.solar_2_in_power}")
        pv_all = float(input_number.solar_1_watts) + float(input_number.solar_2_watts) + float(input_number.solar_1_in_power) + float(input_number.solar_2_in_power)
        #log.warning(f"pv_all {pv_all} type {type(pv_all)}")

        input_number.total_in_power = get_val(["pd.wattsInSum"], url, EcoflowKey, EcoflowSecret, DeltaSnr)
        #was = float(hass.states.get('sensor.' + DeltaName + '_total_in_power').state) #DeltaName unnecessary
        PowerPlus = int(state.get('sensor.shrdzm_' + ShrdzmSnr + '_1_7_0'))
        ##log.warning(f"PowerPlus {PowerPlus}") #shrdzm 1.7 P+ in watts Wirkleistung aktueller Leistungsbezug momentane Leistungsaufnahme

        Automation = state.get('input_boolean.automate') == 'on'
        if int(input_number.battery_charge) < float(state.get('input_number.discharge_limit')):
            #W / 10 #tenths of watts #watts * 10
            #was: set 10W to avoid battery standby as unit_timeout keeps changing to 30 mins
            #is: delta automation to set unit_timeout to Never should keep it from standby
            inv_out_target = 0 #in Morning fill up with all PV what idle and PS took during night
            path = "charge<min"
        else:
            if Automation:
                #inline comment problem: number not allowed after # in following expression?!
                if Morning:
                    #min of pv_all - 20%, P+ and 800 to put most energy into home and at least charge a little
                    inv_out_target = min(math.floor((pv_all - pv_all / 5) / 10) * 10, PowerPlus, 800)
                    path = "auto morning"
                else:
                    inv_out_target = min(PowerPlus, 800) #energy meter P+
                    path = "auto not morning"
                inv_out_target = inv_out_target if inv_out_target >= 0 else 0 #avoid negative value from calculations

                #override energy meter when batt>96% to push max into home and not waste
                #because batt cuts off PV when 100%
                if state.get('input_boolean.override_em') == 'on':
                    #log.warning(f"override_em")
                    if int(input_number.battery_charge) > 96:
                        inv_out_target = 800
                        path = path + "override and chg>96"
                    else:
                        pass
                        path = path + "override and not chg>96"
                set_inv_out_manual(inv_out_target) #feed set or calculated target back to dashboard

            else: #Automation #take inv_out target from dashboard
                inv_out_target = float(state.get('input_number.inv_out_manual'))
                path = "manual"
                #log.warning(f"Manual inv_out_target {inv_out_target}")
        new_perm_w = inv_out_target * 10

        try:
            # ONLY PUT IF SETTINGS CHANGED
            if cur_perm_w == new_perm_w: #== inv_out_target * 10
                pass
                log.warning(f"{path} same inv_out_target {inv_out_target}")
            else:
                params = {"permanentWatts":new_perm_w}
                #payload: 'code': '0', 'message': 'Success', 'eagleEyeTraceId'.., 'tid'
                payload = rest_api("put", url, EcoflowKey, EcoflowSecret, {"sn":PsSnr,"cmdCode":"WN511_SET_PERMANENT_WATTS_PACK","params":params})
                ##log.warning(f"{path} inv_out_target {inv_out_target}")
                task.sleep(10) #wait 10 secs for new check if cur_perm_w and sensor in dash are ACTUAL inv_out_w or last target
                cur_perm_w = get_val(["20_1.permanentWatts"], url, EcoflowKey, EcoflowSecret, PsSnr)
                cur_perm_w = cur_perm_w if cur_perm_w == 0 else round(cur_perm_w / 10)
                sensor.powerstream_1_inverter_output_watts = cur_perm_w #actually previous value (before put_api())
                log.warning(f"{path} sns=cur_perm_w {cur_perm_w}") #inv_out_target shown as out in app!!!

        except Exception as e:
            #traceback_str = traceback.format_exc()
            log.warning(f"set_ef Error putting Ecoflow data {str(e)}")
            #log.warning(traceback_str)
            return

        task.sleep(sleep)
