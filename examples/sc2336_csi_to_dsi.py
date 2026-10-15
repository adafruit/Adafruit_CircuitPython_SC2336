# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# CSI -> DSI live camera demo for the ESP32-P4-Function-EV board.
#
# Pipeline:
#   SC2336 sensor (I2C config, HD 1280x720 RAW10 @30fps, 2 lanes @ 405 Mbps,
#   output window trimmed to the panel size)
#   -> MIPI CSI-2 receiver (mipicsi.Camera)
#   -> ISP RAW10 -> RGB565 conversion
#   -> videocore.VideoBuffer: the camera DMA's frames straight into the DSI
#      framebuffer at the VideoBuffer's x/y position
#   -> mipidsi.Display: 7" EK79007 1024x600 panel, 2 lanes @ 900 Mbps, 52 MHz DPI

import time

import board
import digitalio
import displayio

# The DSI bus is a singleton owned between VM runs; release any previous run.
displayio.release_displays()

import mipicsi
import mipidsi
import videocore

from adafruit_sc2336 import SC2336, Mode

# Panel reset (held released; pulled down by default on this panel).
panel_reset = digitalio.DigitalInOut(board.IO27)
panel_reset.switch_to_output(value=False)
time.sleep(0.01)
panel_reset.value = True
time.sleep(0.12)

# Byte-packed init sequence (busdisplay format: cmd, size|0x80 delay flag,
# data..., [delay_ms]). Values from the Espressif esp_lcd_ek79007 driver.
#
# Note the delay encoding: size byte 0x80 means "no data bytes, delay follows".
EK79007_INIT = bytes(
    (  # cmd, size|0x80 delay flag, data...
        0xB2,
        0x01,
        0x10,  # PAD_CONTROL: 2 DSI data lanes
        0x80,
        0x01,
        0x8B,  # vendor init
        0x81,
        0x01,
        0x78,
        0x82,
        0x01,
        0x84,
        0x83,
        0x01,
        0x88,
        0x84,
        0x01,
        0xA8,
        0x85,
        0x01,
        0xE3,
        0x86,
        0x01,
        0x88,
        0x11,
        0x80,
        120,  # SLPOUT, delay 120 ms
        0x29,
        0x80,
        20,  # display on, delay 20 ms
    )
)

bus = mipidsi.Bus(frequency=1_000_000_000, num_lanes=2)
display = mipidsi.Display(
    bus,
    EK79007_INIT,
    width=1024,
    height=600,
    hsync_pulse_width=10,
    hsync_back_porch=160,
    hsync_front_porch=160,
    vsync_pulse_width=1,
    vsync_back_porch=23,
    vsync_front_porch=12,
    pixel_clock_frequency=52_000_000,
    backlight_pin=board.IO26,  # LCD PWM (backlight) jumpered to J1 GPIO26
)

i2c = board.I2C()
sensor = SC2336(i2c)
sensor.mode = Mode.HD_1280x720_RAW10_30FPS
# Trim the sensor's output window: the camera DMA's frames contiguously with
# no row stride, so the frame's width must match the framebuffer's rows. The
# height is trimmed to the panel too, so no rows land past the framebuffer.
sensor.width = 1024
sensor.height = 600

# output_format=RGB565 makes the ISP convert the sensor's RAW10 frames to
# RGB565 as they are captured, matching the panel's framebuffer format.
camera = mipicsi.Camera(sensor, output_format=mipicsi.PixelFormat.RGB565)

# The camera DMA's frames straight into the DSI framebuffer.
video = videocore.VideoBuffer(display)
video.play(camera)  # camera frames stream live into the panel

print(
    f"CSI to DSI demo running: camera {sensor.width}x{sensor.height} "
    f"@{sensor.frame_rate} fps, {sensor.lane_bit_rate_mbps} MB/s lane rate"
)
