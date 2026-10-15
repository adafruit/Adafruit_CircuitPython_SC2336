# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Minimal example: configure an SC2336CS camera sensor and its ID."""

import board

from adafruit_sc2336 import SC2336

i2c = board.I2C()
sensor = SC2336(i2c)

print("SC2336 sensor:")
print(f"  output: {sensor.h_res}x{sensor.v_res} @{sensor.frame_rate} fps")
print(f"  lanes: {sensor.data_lanes}, {sensor.lane_bit_rate_mbps} Mbps")
print(f"  exposure: {sensor.exposure} lines, gain: {sensor.gain}")
