# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# Bytearray camera capture demo for the ESP32-P4-Function-EV board.
#
# Pipeline:
#   SC2336 sensor (I2C config, VGA RAW10 @50fps, 2 lanes, output window
#   trimmed to 320x240)
#   -> MIPI CSI-2 receiver (mipicsi.Camera) with ISP RAW10 -> RGB565 conversion
#   -> videocore.VideoBuffer: the camera DMA's frames into a plain bytearray
#      (no framebuffer involved)
#   -> displayio renders the bytearray into the panel's framebuffer each time a
#      frame lands, alongside other group layers
#
# Through a bytearray, capture can be composited with other displayio layers
# and repositioned freely, at the cost of a copy per frame.

import time

import board
import digitalio
import displayio
import framebufferio

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
fb_display = mipidsi.Display(
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
display = framebufferio.FramebufferDisplay(fb_display)

i2c = board.I2C()
sensor = SC2336(i2c)
sensor.mode = Mode.VGA_640x480_RAW10_50FPS
# Trim the sensor's output window to a 320x240 window; h_res and v_res read
# back from this window.
sensor._write_byte(0x3208, 0x01)
sensor._write_byte(0x3209, 0x40)  # output width = 320
sensor._write_byte(0x320A, 0x00)
sensor._write_byte(0x320B, 0xF0)  # output height = 240

# output_format=RGB565 makes the ISP convert the sensor's RAW10 frames to
# RGB565 as they are captured, matching the panel's framebuffer format.
camera = mipicsi.Camera(sensor, output_format=mipicsi.PixelFormat.RGB565)

# Capture each frame into a plain bytearray. displayio bulk copies new frames
# into the display (no color conversion needed with RGB565).
capture = videocore.VideoBuffer(bytearray(320 * 240 * 2))
capture.play(camera)

# Composite the captured video with other displayio layers. The capture
# destination doesn't move with the position; the position of the live video
# within the group is what moves on screen.
root = displayio.Group()
root.append(capture)
capture.x = 350
capture.y = 180
display.root_group = root

print(
    f"Bytearray capture demo running: camera {sensor.h_res}x{sensor.v_res} "
    f"@{sensor.frame_rate} fps captured at {capture.x}, {capture.y}"
)
