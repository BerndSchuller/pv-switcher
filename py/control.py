#
# PV Optimizer / Switcher
# (c) 2021 Bernd Schuller, Michael Otto
# see LICENSE file for licensing information

#
# NORMALIZED SWITCHING THRESHOLD
# in WATT
#
threshold = 1400

# IP Address of the SMA TRIPOWER
host = "192.168.178.36"

# IP Address of the power meter of the second installation
second_host = "192.168.178.46"

#
# INTERVAL between runs in minutes
#
interval = 10

# minimum on time in minutes
minimum_on_time = 20

# maximum on time in minutes
maximum_on_time = 40

#
# OpenWeatherMap API parameters
# set ow_appid=None to disable
ow_appid = None # "_your_api_key_"
ow_lat = "50.766"
ow_lon = "6.611"

#
# GPIO Pin number on the Raspberry PI
# where the relay is connected
# CHOOSE A PIN THAT BOOTS IN 'PULL-DOWN' state
# (i.e. the relay will initially be 'off')
#
gpio_data_pin = 27

#
# MODBUS details
#
# modbus TCP server port
port = 502
#
# want to read total generated power
# (GridMs.TotW)
# see SMA modbus documentation
#
unitID = 3
register_to_read = 30775
number_of_words = 2


#
# SCALING FACTORS
#
scaling_factors_file = "daily-scaling.txt"
scaling_factors = []

#
# Log file
#  contains current time, power, threshold
#  and switching decision
#
log_file = "/home/pi/pv-switching-log.txt"

#
# print debug output
#
debug = False

from modbus import ModbusClient
from os import environ, stat
import re
from time import localtime, sleep, strftime
import sys

#
# For the OpenWeatherMap query
#
if ow_appid is not None:
    try:
        import json
        import requests
    except:
        ow_appid = None
        print("Requests/JSON cannot be imported - disabling")

#
# LED variable controlling the relay
#
try:
    from gpiozero import LED
    relay = LED(gpio_data_pin)
    dry_run = False
except:
    dry_run = True
    pass


def print_config_info():
    print("Base power threshold: %s" % threshold)
    print("Min. ON time = %s" % minimum_on_time)
    periods = int(maximum_on_time / minimum_on_time)
    print("Max. ON time = %s periods of %s minutes each" % (periods, minimum_on_time))
    print("Inverter address: %s:%s" % (host, port))
    print("Balcony power meter address: %s" % second_host)
    print("OpenWeatherMap API enabled: %s" % str(ow_appid is not None))


def load_scaling_factors():
    """ 
    loads scaling factors from file
    """
    global scaling_factors
    scaling_factors = []
    with open(scaling_factors_file, "r") as f:
        while True: 
            line = f.readline()
            if not line:
                break
            try:
                scaling_factors.append(float(line.strip()))
            except:
                pass


def get_current_power():
    """ 
    reads the current power from the SMA converter

    returns: current power, as an integer, in Watt

    error handling: returns 0 if the value is out of 
                    range or could not be read
    """
    tp = ModbusClient(host=host, port=port, unit_id=unitID,
                  auto_open=True, auto_close=True)
    regs = tp.read_holding_registers(register_to_read, number_of_words)
    if regs:
        return regs[1]
    else:
        print("No valid data from converter. Last error: '%s' Last exception: '%s'" %
               (tp.last_error_txt(), tp.last_except_txt(verbose=True)))
        return 0

def get_second_power():
    """
    reads current power of the secondary installation 
    
    returns: current power, as an integer, in Watt

    error handling: returns 0 if the value is out of 
                    range or could not be read
    """
    try:
        url = "http://%s/?m=1" % second_host
        with requests.get(url=url) as res:
            match = re.match(".*Leistung{m}(\d+) W.*", res.text)
            if match is not None:
                return match.group(1)
    except:
        pass
    return 0

def get_current_threshold():
    """ returns the base threshold scaled by a factor from our scaling file """
    yday = localtime().tm_yday
    try:
        scaling_factor = scaling_factors[yday]
    except:
        scaling_factor = 1
    current_threshold = int(threshold * scaling_factor)
    if debug:
        print("Day %s, scaling factor %s ==> threshold %s" % (yday, scaling_factor, current_threshold))
    return current_threshold


def get_weather_prediction(over_threshold):
    """ query OpenWeatherMap API to get an indication 
        if the current conditions are going to be stable 
        for the next hour or so
    """
    if ow_appid is None:
        return True
    url = "http://api.openweathermap.org/data/2.5/onecall?exclude=minutely,daily&lat=%s&lon=%s&appid=%s" % (ow_lat,ow_lon,ow_appid)
    try:
        with requests.get(url=url) as res:
            json = res.json()
        code = json['cod']
        if code!=200:
            raise Exception("%s %s" % (code, json['message']))
        current = json['current']
        next_hour = None
        current_time = current['dt']
        for h in json['hourly']:
            h_time = h['dt']
            if h_time < current_time:
                continue
            if current_time - h_time < 3600:
                next_hour = h
                if debug:
                    print(current)
                    print(h)
                break
            if next_hour is None:
                return True
        sundown = int( (current['sunset']-current['dt']) / 60)
        clouds = next_hour['clouds']
        prediction_time = int((next_hour['dt'] - current_time) / 60)
        # consider it OK if sundown is more than two 'on' periods away
        decision = sundown > 2*minimum_on_time
        # and clouds is not 100%
        decision &= clouds < 100
        if debug:
            print("Sundown in %s minutes, expected clouds in %s mins = %s ==> OK?: %s" % (sundown, prediction_time, clouds, decision))
        return decision
    except Exception  as e:
        print("Error getting weather prediction: %s" % str(e))
    return True


def engage():
    """ switch relay to active """
    if debug:
        print(" ==> engaging")
    if not dry_run:
        relay.on()


def disengage():
    """ switch off the relay """
    if debug:
        print(" ==> disengaging")
    if not dry_run:
        relay.off()


def log(power, power1, power2, threshold, ok):
    with open(log_file, "a") as f:
        d = strftime("%Y-%m-%d %H:%M:%S", localtime())
        if debug:
            print("%s power=%s(%s+%s) threshold=%s engage=%s" % (d, power, power1, power2, threshold, ok))
        if ok:
            switch = 1
        else:
            switch = 0
        f.write("%s %s(%s+%s) %s %s\n" % (d, power, power1, power2, threshold, switch))


def setup_signal_handlers():
    import signal
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)


def shutdown_handler(signum, stackframe):
    disengage()
    sys.exit(0)

#
# MAIN LOOP
#
if __name__ == '__main__':
    setup_signal_handlers()
    load_scaling_factors()
    print_config_info()
    counter = 0
    day = strftime("%Y-%m-%d", localtime())
    periods = int(maximum_on_time / minimum_on_time)

    while True:
        thresh = get_current_threshold()
        power1 = get_current_power()
        power2 = get_second_power()
        power = power1 + power2
        weather_ok = get_weather_prediction(power>thresh)
        ok =  (power > thresh) and weather_ok and counter < periods
        log(power, power1, power2, thresh, ok)
        if ok:
            engage()
            sleep(60 * minimum_on_time)
            counter += 1
        else:
            disengage()
            sleep(60*interval)
            check_day = strftime("%Y-%m-%d", localtime())
            if day != check_day:
                counter = 0
                day = check_day

