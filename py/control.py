#
# PV Optimizer / Switcher
# (c) 2021 Bernd Schuller
# see LICENSE file for licensing information

#
# NORMALIZED SWITCHING THRESHOLD
# in WATT
#
threshold = 1200

# IP Address of the SMA TRIPOWER
host = "192.168.178.36"

#
# INTERVAL between runs in minutes
#
interval = 0.2

# minimum on time in minutes
minimum_on_time = 1

# maximum on time in minutes
maximum_on_time = 5

#
# OpenWeatherMap API parameters
# set ow_appid=None to disable
ow_appid = "5eee7c10832093d69b98f26a7eb6c008"
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
# print debug output
#
debug = True

#
# Log file - will log current power, current threshold
#
log_file = "pv-switching-log.txt"

from modbus import ModbusClient
from os import environ, stat
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
    periods = int(maximum_on_time / minimum_on_time)
    print("Max. ON time = %s periods of %s minutes each" %(periods, minimum_on_time))
    print("Inverter address: %s:%s" % (host,port))
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
        # consider it OK if sundown is more than two periods away
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


def log(power, threshold):
    with open(log_file, "a") as f:
        d = strftime("%Y-%m-%d %H:%M:%S", localtime())
        if debug:
            print("%s power=%s threshold=%s" % (d, power, threshold))
        f.write("%s %s %s \n" % (d, power, threshold))


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
    periods = int(maximum_on_time / minimum_on_time)

    while True:
        thresh = get_current_threshold()
        power = get_current_power()
        weather_ok = get_weather_prediction(power>thresh)
        log(power, thresh)
        if (power > thresh) and weather_ok and counter < periods:
            engage()
            sleep(60 * minimum_on_time)
            counter += 1
        else:
            disengage()
            counter = 0
        sleep(60*interval)
