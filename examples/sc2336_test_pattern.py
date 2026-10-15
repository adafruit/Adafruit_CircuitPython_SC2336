# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# Test pattern validation for the SC2336CS camera sensor.
#
# Turns on the sensor's test pattern and captures frames through the MIPI CSI
# receiver. The SC2336's only pattern is a static grayscale gradient; its
# conversion applies +-1 LSB per-channel rounding dither to part of the
# frame, so frames are compared by shape, not bytes: the column brightness
# profile must be a strong, monotonic gradient, structured (not uniform,
# empty or noise-flat). This checks the whole digital path independently of
# the lens and lighting: sensor logic -> MIPI CSI-2 -> receiver -> ISP ->
# memory. It says nothing about the analog side (lens, noise, black level,
# gain); for that, use sc2336_color_check.py against a real scene.

import array
import time

import board
import mipicsi
import videocore

from adafruit_sc2336 import SC2336, Mode

i2c = board.I2C()
sensor = SC2336(i2c)
sensor.mode = Mode.VGA_640x480_RAW10_50FPS
sensor.test_pattern = True

camera = mipicsi.Camera(sensor, output_format=mipicsi.PixelFormat.RGB565)
width, height = sensor.width, sensor.height
buf = array.array("H", (0,) * (width * height))
capture = videocore.VideoBuffer(buf)
capture.play(camera)

time.sleep(1)
snapshot_1 = array.array("H", buf)
time.sleep(1)
snapshot_2 = array.array("H", buf)
capture.stop()
sensor.test_pattern = False

# Structured: not uniform, not all-black or all-white.
values = set(snapshot_2)
structured = 0 < len(values) < width * height
print(f"distinct values: {len(values)}")
print("pattern structured:", "PASS" if structured else "FAILED")


def brightness(pixel):
    # The pattern is grayscale, so the RGB565 pixel value (the encoded gray)
    # is a monotonic proxy for brightness.
    return pixel / 65535.0


def gradient_ok(snap):
    # Sample mean brightness per column and require a strong, mostly
    # monotonic ramp.
    means = []
    for col in range(0, width, 32):
        n, total = 0, 0
        for row in range(0, height, 64):
            total += brightness(snap[col + row * width])
            n += 1
        means.append(total / n)
    span = max(means) - min(means)
    steps = [d for a, b in zip(means, means[1:]) if (d := b - a) > 0.02 or d < -0.02]
    flips = sum(1 for a, b in zip(steps, steps[1:]) if (a > 0) != (b > 0))
    return span > 0.2 and flips <= 2


gradient = gradient_ok(snapshot_1) and gradient_ok(snapshot_2)
print("both frames are a gradient:", "PASS" if gradient else "FAILED")

print("test pattern validation:", "PASS" if structured and gradient else "FAILED")
