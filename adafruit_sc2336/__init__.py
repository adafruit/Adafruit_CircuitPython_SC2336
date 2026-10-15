# SPDX-FileCopyrightText: Copyright (c) 2026 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_sc2336`
================================================================================

Control an SC2336CS camera sensor over I2C

* Author(s): Scott Shawcroft

Implementation Notes
--------------------

**Hardware:**

The SC2336CS image sensor as found on the ESP32-P4-Function-EV board's camera
connector.

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* The ``mipicsi`` core module (needed for the `SC2336.pixel_format` and
  `SC2336.bayer_order` properties and for capturing frames from the sensor).
"""

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_SC2336.git"


try:
    from micropython import const
except ImportError:

    def const(*args, **kwargs):
        """Micropython const() replacement for host builds."""
        return args[0]


_REG_SENSOR_ID_H = const(0x3107)
_REG_SENSOR_ID_L = const(0x3108)
_SC2336_SENSOR_ID = const(0xCB3A)
_REG_SW_RESET = const(0x0103)
_REG_SLEEP_MODE = const(0x0100)
_REG_SHUTTER_TIME = const(0x3E00)  # 3 bytes; 4 low bits are fractional lines
_REG_DIG_COARSE_GAIN = const(0x3E06)
_REG_DIG_FINE_GAIN = const(0x3E07)
_REG_ANG_GAIN = const(0x3E09)
_REG_FLIP_MIRROR = const(0x3221)
_REG_TEST_PATTERN = const(0x4501)
_REG_TOTAL_HEIGHT = const(0x320E)  # 2 bytes, VTS: lines per frame incl. blanking
_REG_OUT_WIDTH = const(0x3208)  # 2 bytes, output frame width
_REG_OUT_HEIGHT = const(0x320A)  # 2 bytes, output frame height
_REG_OUT_START_X = const(0x3210)  # 2 bytes, output X start (crop offset)
_REG_OUT_START_Y = const(0x3212)  # 2 bytes, output Y start (crop offset)

_EXPOSURE_MIN = const(0x08)
_EXPOSURE_MAX_OFFSET_LINES = const(6)

_STREAMING_ERROR = "sensor is streaming; it must be in standby to change the mode or output window"

from .modes import GAIN_REGS, MODES, REG_DELAY, REG_END, TOTAL_GAIN


class Mode:
    """The sensor output modes, as ``Mode.<name>`` constants."""

    SQUARE_800x800_RAW8_30FPS = 0
    VGA_640x480_RAW10_50FPS = 1
    HD_1280x720_RAW10_30FPS = 2
    HD_1280x720_RAW10_50FPS = 3
    FHD_1920x1080_RAW10_30FPS = 4


class SC2336:
    """Control an SC2336CS camera sensor over I2C"""

    def __init__(self, i2c_bus, *, address=0x30):
        """Configure the sensor over the given I2C bus.

        The sensor is reset, its identity is verified and its default mode
        (``Mode.HD_1280x720_RAW10_30FPS``) is loaded. The sensor remains in
        standby.
        """
        self._i2c = i2c_bus
        self._address = address
        self._mode = None
        self._frame_length_lines = 0
        self._streaming = False

        # Soft reset so we start from a known register state.
        self._update_bits(_REG_SW_RESET, 0, 1, 0x01)
        self._delay_ms(5)

        # Confirm the sensor is present.
        sensor_id = (self._read_byte(_REG_SENSOR_ID_H) << 8) | self._read_byte(_REG_SENSOR_ID_L)
        if sensor_id != _SC2336_SENSOR_ID:
            raise ValueError("No SC2336 found")

        # Load the default mode, leaving the sensor in standby.
        self.mode = Mode.HD_1280x720_RAW10_30FPS

    # --- I2C helpers --------------------------------------------------------

    def _write_byte(self, reg, value):
        while not self._i2c.try_lock():
            pass
        try:
            self._i2c.writeto(self._address, bytes(((reg >> 8) & 0xFF, reg & 0xFF, value)))
        finally:
            self._i2c.unlock()

    def _read_byte(self, reg):
        while not self._i2c.try_lock():
            pass
        try:
            buffer = bytearray(1)
            self._i2c.writeto_then_readfrom(
                self._address, bytes(((reg >> 8) & 0xFF, reg & 0xFF)), buffer
            )
        finally:
            self._i2c.unlock()
        return buffer[0]

    def _update_bits(self, reg, offset, length, value):
        reg_data = self._read_byte(reg)
        mask = ((1 << length) - 1) << offset
        self._write_byte(reg, (reg_data & ~mask) | ((value << offset) & mask))

    def _require_standby(self):
        # The mipicsi receiver is built around the current mode and window.
        # Sensors may only reconfigure in standby; the camera stops streaming
        # (and calls _stop()) when its playback stops.
        if self._streaming:
            raise RuntimeError(_STREAMING_ERROR)

    def _write_mode(self, regs):
        for reg, value in regs:
            if reg == REG_END:
                break
            if reg == REG_DELAY:
                self._delay_ms(value)
            else:
                self._write_byte(reg, value)
                if reg == _REG_SW_RESET:
                    # Give the sensor time to come back from its soft reset
                    # before the rest of the mode table is written.
                    self._delay_ms(5)

    def _delay_ms(self, ms):  # noqa: PLR6301
        # CircuitPython's time module; imported lazily so the module can be
        # imported on host builds for docs and tests.
        import time  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        time.sleep(ms / 1000)

    def _cache_window(self):
        # Cache the output window and crop registers. Called after the mode
        # table is written.
        self._width = (self._read_byte(_REG_OUT_WIDTH) << 8) | self._read_byte(_REG_OUT_WIDTH + 1)
        self._height = (self._read_byte(_REG_OUT_HEIGHT) << 8) | self._read_byte(
            _REG_OUT_HEIGHT + 1
        )
        self._crop_x = (self._read_byte(_REG_OUT_START_X) << 8) | self._read_byte(
            _REG_OUT_START_X + 1
        )
        self._crop_y = (self._read_byte(_REG_OUT_START_Y) << 8) | self._read_byte(
            _REG_OUT_START_Y + 1
        )

    # --- Mode and stream control -------------------------------------------

    @property
    def mode(self):
        """The sensor output mode. Changing modes reloads the sensor's
        configuration, which stops streaming until the sensor is started again."""
        return self._mode

    @mode.setter
    def mode(self, mode):
        if self._mode is not None and mode == self._mode:
            return
        if mode < 0 or mode >= len(MODES):
            raise ValueError("Invalid mode")
        self._require_standby()

        # Loading a mode soft resets the sensor, so stop streaming first. The
        # mode table itself leaves the sensor in standby.
        self._streaming = False
        self._write_mode(MODES[mode][0])
        self._mode = mode

        # Give the sensor time to settle after the mode change before streaming
        # starts (the MIPI PLL needs to lock).
        self._delay_ms(10)

        # Read the frame length to know the exposure limit, and cache the
        # window and crop registers: CircuitPython reads width and height off
        # of the sensor at playback, so they must be cheap and non-I2C.
        vts = (self._read_byte(_REG_TOTAL_HEIGHT) << 8) | self._read_byte(_REG_TOTAL_HEIGHT + 1)
        self._frame_length_lines = vts
        self._cache_window()

    def _start(self):
        """Take the sensor out of standby so it streams frames. Only the
        mipicsi core should call this; it is done by `mipicsi.Camera`."""
        self._streaming = True
        # 0 puts the sensor into standby; 1 resumes streaming.
        self._write_byte(_REG_SLEEP_MODE, 0x01)

    def _stop(self):
        """Put the sensor into standby so it stops streaming. Only the
        mipicsi core should call this; deinitializing `mipicsi.Camera`
        stops the sensor."""
        self._streaming = False
        self._write_byte(_REG_SLEEP_MODE, 0x00)

    # --- Info properties -----------------------------------------------------

    @property
    def bayer_order(self):
        """The Bayer element order of the sensor's RAW output (read-only).
        See `mipicsi.BayerOrder`; the SC2336CS transmits BGGR."""
        # Imported lazily so the library can be imported on boards and hosts
        # that lack the mipicsi core module.
        import mipicsi  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        return mipicsi.BayerOrder.BGGR

    @property
    def width(self):
        """The width of the frames the sensor transmits, in pixels (cached;
        it is updated when the window changes). Writing trims the output
        window of the current mode to this size. It
        must be an even number of pixels and, with `crop_x`, stay within the
        mode's readout window. The sensor must be in standby to change it."""
        return self._width

    @width.setter
    def width(self, width):
        self._require_standby()
        window_width = MODES[self._mode][7]
        if not 0 < width <= window_width or width % 2 != 0 or self.crop_x + width > window_width:
            raise ValueError(
                "width must be an even number of pixels with crop_x + width within "
                f"the mode's {window_width} pixel readout window"
            )
        self._width = width
        self._write_byte(_REG_OUT_WIDTH, width >> 8)
        self._write_byte(_REG_OUT_WIDTH + 1, width & 0xFF)

    @property
    def height(self):
        """The height of the frames the sensor transmits, in lines (cached;
        it is updated when the window changes). Writing trims the output
        window of the current mode to this size. It
        must be an even number of lines and, with `crop_y`, stay within the
        mode's readout window. The sensor must be in standby to change it."""
        return self._height

    @height.setter
    def height(self, height):
        self._require_standby()
        window_height = MODES[self._mode][8]
        if (
            not 0 < height <= window_height
            or height % 2 != 0
            or self.crop_y + height > window_height
        ):
            raise ValueError(
                "height must be an even number of lines with crop_y + height within "
                f"the mode's {window_height} line readout window"
            )
        self._height = height
        self._write_byte(_REG_OUT_HEIGHT, height >> 8)
        self._write_byte(_REG_OUT_HEIGHT + 1, height & 0xFF)

    @property
    def crop_x(self):
        """The X position of the output window within the mode's readout
        window, in pixels (cached; it is updated when the crop changes).
        Writing offsets the start of the crop: crop_x + `width` must
        stay within the mode's readout window. The sensor must be in standby
        to change it."""
        return self._crop_x

    @crop_x.setter
    def crop_x(self, crop_x):
        self._require_standby()
        if not 0 <= crop_x or crop_x % 2 != 0 or crop_x + self.width > MODES[self._mode][7]:
            raise ValueError(
                "crop_x must be an even number of pixels with crop_x + width within "
                f"the mode's {MODES[self._mode][7]} pixel readout window"
            )
        self._crop_x = crop_x
        self._write_byte(_REG_OUT_START_X, crop_x >> 8)
        self._write_byte(_REG_OUT_START_X + 1, crop_x & 0xFF)

    @property
    def crop_y(self):
        """The Y position of the output window within the mode's readout
        window, in lines (cached; it is updated when the crop changes).
        Writing offsets the start of the crop: crop_y + `height` must
        stay within the mode's readout window. The sensor must be in standby
        to change it."""
        return self._crop_y

    @crop_y.setter
    def crop_y(self, crop_y):
        self._require_standby()
        if not 0 <= crop_y or crop_y % 2 != 0 or crop_y + self.height > MODES[self._mode][8]:
            raise ValueError(
                "crop_y must be an even number of lines with crop_y + height within "
                f"the mode's {MODES[self._mode][8]} line readout window"
            )
        self._crop_y = crop_y
        self._write_byte(_REG_OUT_START_Y, crop_y >> 8)
        self._write_byte(_REG_OUT_START_Y + 1, crop_y & 0xFF)

    @property
    def frame_rate(self):
        """The frame rate of the current mode, in frames per second. (read-only)"""
        return MODES[self._mode][3]

    @property
    def pixel_format(self):
        """The pixel format of the frames the sensor transmits. (read-only)"""
        # Imported lazily so the library can be imported on boards and hosts
        # that lack the mipicsi core module.
        import mipicsi  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        return mipicsi.PixelFormat.RAW8 if MODES[self._mode][4] == 8 else mipicsi.PixelFormat.RAW10

    @property
    def lane_bit_rate_mbps(self):
        """The MIPI data lane bit rate of the current mode, in Mbps. (read-only)"""
        return MODES[self._mode][5]

    @property
    def data_lanes(self):
        """The number of MIPI data lanes the sensor transmits on. (read-only)"""
        return MODES[self._mode][6]

    # --- Image control --------------------------------------------------------

    @property
    def exposure(self):
        """The exposure time, in lines of integration. One line is a single
        row time; the value may be fractional in steps of 1/16 line. The
        maximum is the frame length of the current mode minus six lines."""
        value = (
            (self._read_byte(_REG_SHUTTER_TIME) << 16)
            | (self._read_byte(_REG_SHUTTER_TIME + 1) << 8)
            | self._read_byte(_REG_SHUTTER_TIME + 2)
        )
        return value / 16

    @exposure.setter
    def exposure(self, exposure):
        max_exposure = self._frame_length_lines * 16 - _EXPOSURE_MAX_OFFSET_LINES * 16
        value = int(exposure * 16)
        value = max(_EXPOSURE_MIN, min(value, max_exposure))
        self._write_byte(_REG_SHUTTER_TIME, value >> 16)
        self._write_byte(_REG_SHUTTER_TIME + 1, value >> 8)
        self._write_byte(_REG_SHUTTER_TIME + 2, value & 0xFF)

    @property
    def gain(self):
        """The total gain as a multiplier, snapped to the sensor's supported
        steps. 1.0 is unity gain; the sensor supports up to 63.0."""
        fine = self._read_byte(_REG_DIG_FINE_GAIN)
        coarse = self._read_byte(_REG_DIG_COARSE_GAIN)
        analog = self._read_byte(_REG_ANG_GAIN)
        for i, regs in enumerate(GAIN_REGS):
            if regs[0] == fine and regs[1] == coarse and regs[2] == analog:
                return TOTAL_GAIN[i] / 1000
        return 1.0

    @gain.setter
    def gain(self, gain):
        # Total gain is stored in millitimes (1000 == 1x). Find the nearest
        # supported step.
        target = int(gain * 1000)
        target = max(TOTAL_GAIN[0], min(target, TOTAL_GAIN[-1]))
        best = 0
        best_distance = 1 << 31
        for i, total in enumerate(TOTAL_GAIN):
            distance = abs(total - target)
            if distance < best_distance:
                best_distance = distance
                best = i
        self._write_byte(_REG_DIG_FINE_GAIN, GAIN_REGS[best][0])
        self._write_byte(_REG_DIG_COARSE_GAIN, GAIN_REGS[best][1])
        self._write_byte(_REG_ANG_GAIN, GAIN_REGS[best][2])

    @property
    def flip_x(self):
        """Mirror the image horizontally."""
        return (self._read_byte(_REG_FLIP_MIRROR) & 0x06) != 0

    @flip_x.setter
    def flip_x(self, flip):
        self._update_bits(_REG_FLIP_MIRROR, 1, 2, 0x03 if flip else 0x00)

    @property
    def flip_y(self):
        """Flip the image vertically."""
        return (self._read_byte(_REG_FLIP_MIRROR) & 0x60) != 0

    @flip_y.setter
    def flip_y(self, flip):
        self._update_bits(_REG_FLIP_MIRROR, 5, 2, 0x03 if flip else 0x00)

    @property
    def test_pattern(self):
        """Output the sensor's test pattern instead of image data. Useful for
        checking the signal path independently of the lens and lighting."""
        return (self._read_byte(_REG_TEST_PATTERN) & 0x08) != 0

    @test_pattern.setter
    def test_pattern(self, enable):
        self._update_bits(_REG_TEST_PATTERN, 3, 1, 0x01 if enable else 0x00)

    @property
    def standby(self):
        """True when the sensor is in standby and not streaming (read-only).
        Loading a mode puts the sensor into standby. Playing a
        `mipicsi.Camera` from the sensor starts the sensor; stopping playback
        stops it; deinitializing the camera puts it back into standby."""
        return not self._streaming
