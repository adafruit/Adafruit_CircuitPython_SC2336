CSI to DSI direct
-----------------

Live camera video on the ESP32-P4-Function-EV board: SC2336 camera -> MIPI CSI
receiver -> ISP -> DMA straight into the MIPI DSI framebuffer. The sensor's
output window is trimmed to the panel size because the camera DMA's whole
frames.

.. literalinclude:: ../examples/sc2336_csi_to_dsi.py
    :caption: examples/sc2336_csi_to_dsi.py
    :linenos:

Capture through a bytearray
---------------------------

Capturing into a plain `bytearray` lets displayio composite the live video
with other layers. The sensor's output window is trimmed to a 320x240 capture
window; displayio copies each frame into the panel.

.. literalinclude:: ../examples/sc2336_capture_bytearray.py
    :caption: examples/sc2336_capture_bytearray.py
    :linenos:
