# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Ensure your SC2336 works: configure it over I2C and capture a frame."""

import time

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
buf = bytearray(width * height * 2)
capture = videocore.VideoBuffer(buf)
capture.play(camera)
print(f"Playing, capturing {width}x{height} frames")

# Print the video as UTF-8 brightness blocks on the serial console. Each
# character is a 16x32 pixel block of the frame (40x15 blocks). Reading the
# buffer repeatedly shows the moving video and confirms frames land.
SHADES = " ░▒▓█"
BLOCK_W, BLOCK_H = 16, 32
while True:
    for row in range(height // BLOCK_H):
        line = ""
        for col in range(width // BLOCK_W):
            x = col * BLOCK_W
            y = row * BLOCK_H
            i = 2 * (x + y * width)  # little-endian RGB565
            pixel = buf[i] | (buf[i + 1] << 8)
            r = (pixel >> 11) & 0x1F
            g = (pixel >> 5) & 0x3F
            b = pixel & 0x1F
            line += SHADES[(2 * r + 5 * g + b) * (len(SHADES) - 1) // (2 * 31 + 5 * 63 + 31)]
        print(line)
    print()
    time.sleep(1)
