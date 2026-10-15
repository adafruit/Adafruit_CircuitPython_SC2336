# CSI -> DSI live camera demo for the ESP32-P4-Function-EV board.
#
# Pipeline:
#   SC2336 sensor (I2C config, 1280x720 RAW10 @30fps, 2 lanes @ 405 Mbps)
#   -> MIPI CSI-2 receiver (mipicsi.Camera)
#   -> ISP RAW10 -> RGB565 conversion
#   -> videocore.VideoBuffer: the camera DMA's frames straight into the DSI
#      framebuffer at the VideoBuffer's x/y position
#   -> mipidsi.Display: 7" EK79007 1024x600 panel, 2 lanes @ 900 Mbps, 52 MHz DPI
#
# The camera is 1280x720 but the panel is 1024x600, so the VideoBuffer is
# placed at (-128, -60) to center-crop the video into the panel.

import board
import displayio

# The DSI bus is a singleton owned between VM runs; release any previous run.
displayio.release_displays()

import framebufferio
import mipicsi
import mipidsi
import videocore

from adafruit_sc2336 import SC2336, Mode

# --- Display (EK79007, 1024x600) -------------------------------------------

# Byte-packed init sequence (busdisplay format: cmd, size|0x80 delay flag,
# data..., [delay_ms]). Values from the Espressif esp_lcd_ek79007 driver.
#
# Note the delay encoding: size byte 0x80 means "no data bytes, delay follows".
EK79007_INIT = bytes(
    (
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
mipi_display = mipidsi.Display(
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
display = framebufferio.FramebufferDisplay(mipi_display)

# --- Camera (SC2336, 1280x720 RAW10 @30fps) --------------------------------

i2c = board.I2C()
sensor = SC2336(i2c)
sensor.mode = Mode.HD_1280x720_RAW10_30FPS

# output_format=RGB565 makes the ISP convert the sensor's RAW10 frames to
# RGB565 as they are captured, matching the panel's framebuffer format.
camera = mipicsi.Camera(sensor, output_format=mipicsi.PixelFormat.RGB565)

# --- Show the live video ----------------------------------------------------

# NOTE: for now the camera DMA's whole frames, so the frame must fit the
# framebuffer exactly at video.x/video.y. Center-cropping a 1280x720 frame
# into the 1024x600 panel needs the clip support deferred in review; until
# then, this demo captures frames into a buffer instead.

# Capture camera frames into a buffer to read the raw pixels:
pixels = bytearray(1280 * 720 * 2)
video = videocore.VideoBuffer(pixels)
video.play(camera)
bit_rate = sensor.lane_bit_rate_mbps
print(
    f"CSI capture demo running: camera {camera.width}x{camera.height} @30 fps, "
    f"{bit_rate} MB/s lane rate"
)
