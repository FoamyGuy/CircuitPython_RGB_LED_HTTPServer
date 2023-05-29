Introduction
============


.. image:: https://readthedocs.org/projects/circuitpython-rgb-led-httpserver/badge/?version=latest
    :target: https://circuitpython-rgb-led-httpserver.readthedocs.io/
    :alt: Documentation Status



.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/foamyguy/CircuitPython_RGB_LED_HTTPServer/workflows/Build%20CI/badge.svg
    :target: https://github.com/foamyguy/CircuitPython_RGB_LED_HTTPServer/actions
    :alt: Build Status


.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Code Style: Black

Control Neopixels or Dotstars over the network with an HTTP API that runs in CircuitPython.


Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.

Installing from PyPI
=====================

On supported GNU/Linux systems like the Raspberry Pi, you can install the driver locally `from
PyPI <https://pypi.org/project/circuitpython-rgb-led-httpserver/>`_.
To install for current user:

.. code-block:: shell

    pip3 install circuitpython-rgb-led-httpserver

To install system-wide (this may be required in some cases):

.. code-block:: shell

    sudo pip3 install circuitpython-rgb-led-httpserver

To install in a virtual environment in your current project:

.. code-block:: shell

    mkdir project-name && cd project-name
    python3 -m venv .venv
    source .env/bin/activate
    pip3 install circuitpython-rgb-led-httpserver

Installing to a Connected CircuitPython Device with Circup
==========================================================

Make sure that you have ``circup`` installed in your Python environment.
Install it with the following command if necessary:

.. code-block:: shell

    pip3 install circup

With ``circup`` installed and your CircuitPython device connected use the
following command to install:

.. code-block:: shell

    circup install rgb_led_httpserver

Or the following command to update an existing version:

.. code-block:: shell

    circup update

Usage Example
=============

.. code-block:: python

    from rgb_server import RGBLedServer

    server_process = RGBLedServer()

    while True:
        server_process.animate()
        server_process.poll()

Documentation
=============
API documentation for this library can be found on `Read the Docs <https://circuitpython-rgb-led-httpserver.readthedocs.io/>`_.

For information on building library documentation, please check out
`this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/foamyguy/CircuitPython_RGB_LED_HTTPServer/blob/HEAD/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
