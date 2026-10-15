Simple test
-----------

Ensure the sensor is detected and captures frames.

.. literalinclude:: ../examples/sc2336_simpletest.py
    :caption: examples/sc2336_simpletest.py
    :linenos:

CSI to DSI direct
-----------------

Live camera video on the ESP32-P4-Function-EV board: SC2336 camera -> MIPI CSI
receiver -> ISP -> DMA straight into the MIPI DSI framebuffer. The sensor's
output window is trimmed to the panel size because the camera DMA's whole
frames.

.. literalinclude:: ../examples/sc2336_csi_to_dsi.py
    :caption: examples/sc2336_csi_to_dsi.py
    :linenos:

Capture through an array
------------------------

Capturing into an `array` of 16-bit unsigned pixels (`"H"`, two bytes per
pixel) lets displayio composite the live video
with other layers. The sensor's output window is trimmed to a 320x240 capture
window; displayio copies each frame into the panel.

.. literalinclude:: ../examples/sc2336_capture_array.py
    :caption: examples/sc2336_capture_array.py
    :linenos:

Test pattern validation
-----------------------

Turn on the sensor's test pattern, capture it into an array of 2-byte pixels,
and validate
it end to end.

.. literalinclude:: ../examples/sc2336_test_pattern.py
    :caption: examples/sc2336_test_pattern.py
    :linenos:

Color processing check
----------------------

The color path (Bayer order through the ISP's RAW to RGB565 conversion)
checked against a real scene: the channel that dominates each Bayer position
must match the sensor's reported `mipicsi.BayerOrder`.

.. literalinclude:: ../examples/sc2336_color_check.py
    :caption: examples/sc2336_color_check.py
    :linenos:

Test pattern cycle
------------------

The csi to DSI example modified to cycle every single-bit change of the
sensor's test pattern registers on the panel, to discover which register
value produces which image.

.. literalinclude:: ../examples/sc2336_pattern_cycle.py
    :caption: examples/sc2336_pattern_cycle.py
    :linenos:
