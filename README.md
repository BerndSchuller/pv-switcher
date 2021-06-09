# PV Switcher / Optimizer for SMA inverter and Raspberry PI

This program written for the Raspberry PI is designed to switches a
single relay connected to one of the GPIO pins on on the PI, based on
the currently generated power from the SMA inverter and other factors, such
as a configurable threshold, and potentially the expected weather.

The minimum and maximum "ON" time can be configured as well.

Requires a connection via TCP to the modbus server on the SMA inverter.
The IP address of the inverter (and possibly other modbus parameters)
must be configured as well.

Configuration is done at the beginning of the file "py/control.py"

You can install this tool as a service on the Raspberry PI by running
'make install-service'
