# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Ensure your SC2336 works: configure it over I2C and capture a frame."""

import board
import mipicsi
import videocore

from adafruit_sc2336 import SC2336, Mode

i2c = board.I2C()
sensor = SC2336(i2c)
sensor.mode = Mode.VGA_640x480_RAW10_50FPS

print("SC2336 sensor:")
print(f"  output: {sensor.width}x{sensor.height} @{sensor.frame_rate} fps")
print(f"  lanes: {sensor.data_lanes}, {sensor.lane_bit_rate_mbps} Mbps")
print(f"  exposure: {sensor.exposure} lines, gain: {sensor.gain}")

# Capture frames into a plain bytearray so Python can work with the pixels.
camera = mipicsi.Camera(sensor, output_format=mipicsi.PixelFormat.RGB565)
width, height = sensor.width, sensor.height
capture = videocore.VideoBuffer(bytearray(width * height * 2))
capture.play(camera)
print(f"Playing, capturing {width}x{height} frames")
