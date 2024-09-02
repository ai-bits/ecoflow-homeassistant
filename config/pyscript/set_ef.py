# v0.2.13 20240902 0940 as get_ef()? see issue for description

# get / set data via EF official API
# based on https://github.com/svenerbe/ecoflow_dynamic_power_adjustment

# prerequisites to control inverter_output_watts on PowerStream:
# EcoFlow account
# Request dev status at https://developer-eu.ecoflow.com/
#   to get access to the EcoFlow API (key and secret)
# HomeAssistant Supervised on HAOS or Docker + HACS + EcoFlowCloud +
#   (Visual) Studio Code (Server) + PyScript

# HA secrets.yaml: paste Ecoflow (access) key, Ecoflow secret (key),
#   PowerStream snr, Delta snr, energy meter id

# HA configuration.yaml: check what items you need for set_ef.py
#   and dashboards

# HA automations.yaml: compare the code if an entry exists in HA VS Code
# The automation.ecoflow example here is triggered every minute and
#   calls set_ef.py with the arguments in automations.yaml data:

# HA pyscript/set_ef.py (NOT in custom_components/pyscript!)
#   En/disable in Settings > Automations

# HA dashboards: Leave the Overview alone, add a dummy with any content
#   or name (will be replaced with what's in - title:),
#   in RAW dash editing mode (Add Dashboard, Edit, ... RAW Configuration Editor)
#   replace the dummy YAML code with the 1- or 2-column sample YAML
#   and find and replace PS and Delta name parts, eg the hw51123456789012 placeholder in
#   sensor.hw51123456789012_inverter_output_watts with your device's name or snr
#   (and shrdzm mac-address with actual one or Shelly,.. credentials)

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

def hmac_sha256(data, key):
    hashed = hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).digest()
    sign = binascii.hexlify(hashed).decode('utf-8')
    return sign

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

def put_api(url, key, secret, params=None):
    nonce     = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers   = {'accessKey':key,'nonce':nonce,'timestamp':timestamp}
    sign_str  = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = task.executor(requests.put, url, headers=headers, json=params)
    if response.status_code == 200: return response.json()
    else: print(f"put_api: {response.text}")

def get_api(url, key, secret, params=None):
    nonce     = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers   = {'accessKey':key,'nonce':nonce,'timestamp':timestamp}
    sign_str  = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = task.executor(requests.get, url, headers=headers, json=params)
    if response.status_code == 200: return response.json()
    else: print(f"get_api: {response.text}")

def post_api(url, key, secret, params=None):
    nonce     = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))
    headers   = {'accessKey':key,'nonce':nonce,'timestamp':timestamp}
    sign_str  = (get_qstr(get_map(params)) + '&' if params else '') + get_qstr(headers)
    headers['sign'] = hmac_sha256(sign_str, secret)
    response = task.executor(requests.post, url, headers=headers, json=params)
    #if response.status_code == 200: return response.json()
    if response.status_code == 200: return response
    else: print(f"post_api: {response.text}")

def check_if_device_is_online(SN=None, payload=None):

    parsed_data = payload
    desired_device_sn = SN

    device_found = False

    for device in parsed_data.get('data', []):
        if device.get('sn') == desired_device_sn:
            device_found = True
            online_status = device.get('online', 0)

            if online_status == 1:
                print(f"device with SN '{desired_device_sn}' is online.")
                return "online"
            else:
                print(f"device with SN '{desired_device_sn}' is offline.")
                return "offline"
    if not device_found:
        print(f"device with SN '{desired_device_sn}' not found in data.")
        return "devices not found"

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

#get_device_name from Snr when used instead of Snr
def get_device_name(SN, payload):
    for device in payload.get('data', []):
        if device.get('sn') == SN:
            return device.get('deviceName', 'Unknown')
    return 'Device not found'

def set_inv_out_manual(value):
    service.call("input_number", "set_value", entity_id="input_number.inv_out_manual", value=value)

def set_morning(value, value2):
    if value: service.call("input_boolean", "turn_on", entity_id="input_boolean.morning")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.morning")
    if value2: service.call("input_boolean", "turn_on", entity_id="input_boolean.ran_today")
    else: service.call("input_boolean", "turn_off", entity_id="input_boolean.ran_today")

#parameters with default (was: Automation=False) must go behind others
@service
def set_ef(EcoflowKey=None, EcoflowSecret=None, PsSnr=None, DeltaSnr=None, ShrdzmSnr=None):
    if PsSnr is None:
        log.warning(f"PsSnr=None, exiting") 
        return
    url = 'https://api-e.ecoflow.com/iot-open/sign/device/quota' #api-e. instead of api. according to Günther Nid FB
    url_device = 'https://api-e.ecoflow.com/iot-open/sign/device/list' #api-e. instead of api.
    # (access) key & secret (key) from secrets.yaml
    key = EcoflowKey
    secret = EcoflowSecret
    # collect status of the devices
    payload = get_api(url_device,key,secret,{"sn":PsSnr})
    check_ps_status = check_if_device_is_online(PsSnr, payload)
    #PsName = 'powerstream_1' #unnecessary; was quick fix where PsSnr didn't work any more after ha changes
    #DeltaName = 'delta_2_max_2'

    #only pass secrets as parms; other values public anyway
    #parms added: ShrdzmSnr
    #parms removed, replaced by direct state.get() when necessary:
    #, InvOutManual=None, was BatteryCharge=None, PowerPlus=None, Automation=False
    InvOutManual = float(state.get('input_number.inv_out_manual'))

    #get_val for needed states; for field names see
    #https://developer-eu.ecoflow.com/us/document/powerStreamMicroInverter
    cur_perm_w = get_val(["20_1.permanentWatts"], url, key, secret, PsSnr)
    cur_perm_w = cur_perm_w if cur_perm_w == 0 else round(cur_perm_w / 10)
    input_number.battery_charge = get_val(["20_1.batSoc"], url, key, secret, PsSnr)
    input_number.solar_1_watts = round(get_val(["20_1.pv1InputWatts"], url, key, secret, PsSnr) / 10)
    input_number.solar_2_watts = round(get_val(["20_1.pv2InputWatts"], url, key, secret, PsSnr) / 10)
    input_number.solar_1_in_power = get_val(["pd.pv1ChargeWatts"], url, key, secret, DeltaSnr)
    input_number.solar_2_in_power = get_val(["pd.pv2ChargeWatts"], url, key, secret, DeltaSnr)
    #log.warning(f"input_number.solar_1_in_power {input_number.solar_1_in_power}")
    #log.warning(f"input_number.solar_2_in_power {input_number.solar_2_in_power}")
    pv_all = input_number.solar_1_watts + input_number.solar_2_watts + input_number.solar_1_in_power + input_number.solar_2_in_power

    input_number.total_in_power = get_val(["pd.wattsInSum"], url, key, secret, DeltaSnr)
    #was = float(hass.states.get('sensor.' + DeltaName + '_total_in_power').state) #DeltaName unnecessary
    PowerPlus = int(state.get('sensor.shrdzm_' + ShrdzmSnr + '_1_7_0'))
    #log.warning(f"PowerPlus {PowerPlus}") #shrdzm 1.7 P+ in watts Wirkleistung aktueller Leistungsbezug momentane Leistungsaufnahme
    Automation = state.get('input_boolean.automate') == 'on'

    # sunset = datetime.fromisoformat(hass.states.get('sensor.sun_next_setting').state) #.hour
    # now = datetime.now().hour
    # log.warning(f"sunset {sunset}")
    # log.warning(f"now {now}")

    Morning = state.get('input_boolean.morning') == 'on'
    #log.warning(f"Morning {Morning}")
    #SunriseNextTime = state.get('sensor.sunrise_next_time')
    #hm = datetime.now().strftime('%H:%M')
    #log.warning(f"hm {hm} SunriseNextTime {SunriseNextTime}")
    RanToday = state.get('input_boolean.ran_today') == 'on'
    if datetime.now().strftime('%H:%M') == state.get('sensor.sunrise_next_time'): #sunrise
        Morning = True
        RanToday = False
    if Morning and int(input_number.battery_charge) == 100:
        Morning = False
        RanToday = True
    #log.warning(f"Morning {Morning} RanToday {RanToday}")
    set_morning(Morning, RanToday) #feed back Morning to morning and RanToday to ran_today

    try:
        #gue
        #InvOutManual target = DASHBOARD INPUT, actual out depends on batt full and feed-in ctl, inv temp throttling
        #  WAS TotalPower was W ENERGY METER
        #inverter_output_watts see condition comments below

        #float(state.get() INSTEAD OF state.get() or int(state.get() for slider (eg discharge_limit) because:
        #Error fetching Ecoflow data invalid literal for int() with base 10: '65.0'

        #discharge_limit min and max can be set in configuration.yaml; in app set 0% and 100%; pyscript takes care
        #Delta often ignores values in app anyway; save for emergency
        #discharge_limit min is 30% to keep batt from standby at 20% when it used < 10%points in idle
        if int(input_number.battery_charge) < float(state.get('input_number.discharge_limit')):
            #W / 10 #tenths of watts #watts * 10
            #was: set 10W to avoid battery standby as unit_timeout keeps changing to 30 mins
            #is: delta automation to set unit_timeout to Never should keep it from standby
            InvOutManual = 0 #in Morning fill up with all PV what idle and PS took during night
        else:
            #log.warning(f"Automation {Automation}")
            if Automation:
                #inline comment problem: number not allowed after # in following expression?!
                if Morning:
                    #min of pv_all - 20%, P+ and 800 to put most energy into home and at least charge a little
                    InvOutManual = min(math.floor((pv_all - pv_all / 5) / 10) * 10, PowerPlus, 800)
                else:
                    InvOutManual = min(PowerPlus, 800) #energy meter P+
                InvOutManual = InvOutManual if InvOutManual >= 0 else 0 #avoid negative value from calculations

                #override energy meter when batt>96% to push max into home and not waste
                #because batt cuts off PV when 100%
                if state.get('input_boolean.override_em') == 'on':
                    #log.warning(f"override_em")
                    if int(input_number.battery_charge) > 96:
                        InvOutManual = 800
                set_inv_out_manual(InvOutManual) #feed set or calculated target back to dashboard

            else: #Automation #take inv_out target from dashboard
                InvOutManual = float(state.get('input_number.inv_out_manual'))
                #log.warning(f"Manual InvOutManual {InvOutManual}")
        new_perm_w = InvOutManual * 10

        # ONLY PUT IF SETTINGS CHANGED
        if not cur_perm_w == new_perm_w: #== InvOutManual * 10
            params = {"permanentWatts":new_perm_w}
            cmdCode = 'WN511_SET_PERMANENT_WATTS_PACK' #used only once; next: use string itself
            payload = put_api(url,key,secret,{"sn":PsSnr,"cmdCode":cmdCode,"params":params})
            return payload #why return?

    except Exception as e:
        log.warning(f"Error fetching Ecoflow data {str(e)}")
        return