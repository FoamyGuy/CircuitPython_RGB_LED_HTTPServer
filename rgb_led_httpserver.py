# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: MIT
"""
`rgb_led_httpserver`
================================================================================

Control Neopixels or Dotstars over the network with an HTTP API that runs in CircuitPython.


* Author(s): Tim C

Implementation Notes
--------------------

**Hardware:**

  * `NeoPixels <https://www.adafruit.com/category/168>`_
  * `DotStars <https://www.adafruit.com/search?q=DotStars>`_
  * `ESP32 S2 Based MCUs <https://www.adafruit.com/search?q=ESP32-S2>`_
  * `ESP32 S3 Based MCUs <https://www.adafruit.com/search?q=ESP32-S3>`_
  * `Raspberry Pi PicoW <https://www.adafruit.com/product/5526>`_


**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads


"""
# pylint: disable=too-many-lines

import os
import board
import neopixel
import adafruit_dotstar as dotstar
import socketpool
import wifi
from adafruit_httpserver import (
    Server,
    Request,
    JSONResponse,
    POST,
    BAD_REQUEST_400,
    GET,
)
from adafruit_httpserver.authentication import (
    Bearer,
    require_authentication,
)

try:
    from typing import Tuple, Union
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/foamyguy/CircuitPython_RGB_LED_HTTPServer.git"

ANIMATION_CLASSES = {
    "blink": ("adafruit_led_animation.animation.blink", "Blink"),
    "colorcycle": ("adafruit_led_animation.animation.colorcycle", "ColorCycle"),
    "comet": ("adafruit_led_animation.animation.comet", "Comet"),
    "rainbow": ("adafruit_led_animation.animation.rainbow", "Rainbow"),
}


def rgb_to_hex(tuple_color: Tuple[int, int, int]) -> int:
    """
    Convert tuple RGB color to hex int i.e. (255, 0, 0) -> 0xff0000
    :param tuple_color: The color to convert as a tuple with 0-255 ints
    for each color channel.

    :return: The numerical value equal to hex color.
    """
    return (
        (int(tuple_color[0]) << 16) + (int(tuple_color[1]) << 8) + int(tuple_color[2])
    )


def convert_color_to_num(color_str: Union[str, int, Tuple[int, int, int]]):
    """
    Convert an RGB tuple, or string in the hex forms of 0x00ff00 or #ff00ff into a number.

    :param color_str:  hex color with 0x or # prefix
    :return int: the color as a number
    """
    if isinstance(color_str, int):
        # if it's already a number just return it
        return color_str
    if isinstance(color_str, str):
        if color_str.startswith("#"):
            _cur_value = color_str.replace("#", "0x")
        return int(color_str, 0)
    if isinstance(color_str, (list)):
        return color_str

    raise ValueError("Invalid input for 'color_str'")


def import_animation_contructor(anim):
    """
    Imports a given animation class and returns the constructor function
    that can be used to create an instance of it.

    :param anim: shorthand animation name key. See ANIMATION_CLASSES.keys()
      for valid values
    :return: None
    """
    if anim not in ANIMATION_CLASSES:
        return None

    base_module = __import__(ANIMATION_CLASSES[anim][0])
    anim_submodule = getattr(base_module, "animation")
    specific_anim_module = getattr(anim_submodule, anim)
    constructor = getattr(specific_anim_module, ANIMATION_CLASSES[anim][1])
    return constructor


class RGBLedServer:
    """
    Non-Blocking HTTP server that implements a JSON based API for controlling NeoPixels, WS2812, or DotStar RGB LEDs.

    :param request: Request object
    :return: JSONResponse

    General API Information:
    ************************

    Terminology:
    ############

    ``pixel``: A single RGB capable LED. The term is used independently of the actual protocol being used to
      communicate with the LED. A single LED in a Neopixel strip, and a single LED in a DotStar strip are considered
      to be a ``pixel`` under this definition.

    ``strip``: One or more ``pixels`` connected in series. The term is used independently of the protocol used.
      Both Neopixels and DotStars are considered ``strips``

    ``strip_id``: A unique string that represents an initialized strip. Can be supplied by the user, or generated
      by default from pin names.

    Request Body:
    #############

    All POST requests should send a response body containing a valid JSON encoded
    string.

    Response Body:
    ##############

    All requests will be responded to with a response body containing a valid JSON encoded
    string. The ``success`` field will have a boolean value indicating success of the operation.
    Other fields are included as needed by specific endpoints.

    Valid Color Formats:
    ####################

    For all endpoints that take argument(s) representing colors there are two valid
    value formats:

    * str containing hex notation prepended with "0x" example: ``"0x00ff00"``
    * list containing 3 or 4 ints 0-255 representing RGB color values. example: ``[255, 0, 255]``

    Authentication (Optional)
    #########################

    To enable token based authentication add a value ``HTTP_RGB_BEARER_AUTH`` inside of your settings.toml file.
    The value should be a token string. If this configuration is present then all
    HTTP endpoints will require this token to be passed in the Authentication header.

    Example settings.toml config::

        HTTP_RGB_BEARER_AUTH="cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk"

    Example Request Auth Header::

        Authorization: Bearer cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk

    Un-authorized requests will be returned ``401 Unauthorized`` responses.

    HTTP API Endpoints:
    *******************

    Initialize Neopixels:
    #####################

    URL: ``/init/neopixels/``

    Method(s): POST

    Details: Initialize a strip of Neopixels with 1 or more pixels on it.

    **************
    Required Args:
    **************

    :pin: str | The pin name that the strip is connected to
        as it appears on the `board` object.
    :pixel_count: int | The number of LEDs in the strip.

    **************
    Optional Args:
    **************

    :parameter id: str | The ID to be used to refer to the initialized strip
        with requests in the future.
    :parameter kwargs: dict | Dictionary of keyword arguments to pass along
      to the Neopixel class constructor. Commonly used kwargs include: brightness,
      bpp, auto_write. See Neopixel library for comprehensive list.

    *********************
    Return Object Fields:
    *********************

        :success: bool | Whether the strip was initialized successfully.
        :strip_id: str | The ``strip_id`` that was assigned to the strip if it was
            successfully initialized. This will be the value of the ``id`` argument
            if it was passed, or a default strip_id generated from the pins used
            if ``id`` was not passed.



    Example Request Data Body::

        {
          "pin" : "NEOPIXEL",
          "pixel_count": 1,
          "kwargs":{
            "brightness": 0.01,
            "bpp": 3,
            "auto_write": true
          }
        }

    Example Successful Response(s)::

        {
          "success": true,
          "strip_id": "NEOPIXEL"
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Invalid Pin: NOT_NEOPIXEL"
        }

    Initialize Dotsars:
    #####################

    URL: ``/init/dotstars/``

    Method(s): POST

    Details: Initialize a strip of DotStars with 1 or more pixels on it.

    **************
    Required Args:
    **************

    :data_pin: str | The data pin name that the strip is connected to
        as it appears on the `board` object.
    :clock_pin: str | The clock pin name that the strip is connected to
        as it appears on the `board` object.
    :pixel_count: int | The number of LEDs in the strip.

    **************
    Optional Args:
    **************

    :parameter id: str | The ID to be used to refer to the initialized strip
        with requests in the future.
    :parameter kwargs: dict | Dictionary of keyword arguments to pass along
        to the DotStar class constructor. Commonly used kwargs include: brightness,
        bpp, auto_write. See Neopixel library for comprehensive list.

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the strip was initialized successfully.
    :strip_id: str | The ``strip_id`` that was assigned to the strip if it was
        successfully initialized. This will be the value of the ``id`` argument
        if it was passed, or a default strip_id generated from the pins used
        if ``id`` was not passed.

    Example Request Data Body::

        {
          "clock_pin" : "D9",
          "data_pin" : "MOSI",
          "pixel_count": 30,
          "kwargs":{
            "brightness": 0.1,
            "auto_write": true
          }
        }

    Example Successful Response(s)::

        {
          "success": true,
          "strip_id": "D9MOSI"
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Invalid Pin: MOSI"
        }

    GET or SET Pixels:
    ##################

    URL: ``/pixels/<strip_id>/``

    Method(s): GET, POST

    Details: Get or set the color of pixels within a strip. If the pixels are being set
    and the strip is currently in animation mode, it will be switched back to
    pixels mode.

    ***************
    Path Arguments:
    ***************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.

    ***********************
    Required Args for POST:
    ***********************

    :pixels: Union[dict, list] | A dictionary with pixel indexes as keys
        and colors as values. Or a list containing color values where index within
        the list will map to index within the strip.

    **************
    Optional Args:
    **************

    :blank_pixels: bool | Whether to clear the pixels to blank before setting
        the given new colors.

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the operation was completed successfully.

    Example Request Data Body::

        {
          "blank_pixels": true,
          "pixels": {
            "12": "0xff0000",
            "13": "0x00ff00"
            "17": "0xff00ff"
          }
        }

    Example Successful Response(s)::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Pixels must be list or dictionary"
        }

    Write:
    ######

    URL: ``/write/<strip_id>/``

    Method(s): POST

    Details: Call ``write()`` on the specified strip. Generally only needed if ``auto_write`` is ``False`` on
      the strip. This will write any pending color change operations to the strip.

    ***************
    Path Arguments:
    ***************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the operation was completed successfully.

    Example Successful Response(s)::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Strip D9 is not initialized"
        }

    Fill:
    #####

    URL: ``/fill/<strip_id>/``

    Method(s): POST

    Details: Fill the specified strip with the given color

    ***************
    Path Arguments:
    ***************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.

    ***********************
    Required Args for POST:
    ***********************

    :color: str | The color to fill the strip with

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the operation was completed successfully.

    Example Request Data Body::

        {
        "color": "0x0000ff"
        }

    Example Successful Response(s)::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Strip D9 is not initialized"
        }

    Get or Set Brightness:
    ######################

    URL: ``/brightness/<strip_id>/``

    Method(s): GET, POST

    Details: Get or Set the brightness value for a strip.

    ***************
    Path Arguments:
    ***************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.

    ***********************
    Required Args for POST:
    ***********************

    :brightness: float | The brightness level to set on the strip between 0.0 - 1.0

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the operation was completed successfully.

    Example POST Request Data Body::

        {
        "brightness": 0.1
        }

    Example Successful Response from GET::

        {
          "success": true,
          "brightness": 0.1
        }

    Example Successful Response from POST::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Strip D9 is not initialized"
        }

    Get or Set Auto Write:
    ######################

    URL: ``/auto_write/<strip_id>/``

    Method(s): GET, POST

    Details: Get or Set the auto_write value for a strip.

    ***************
    Path Arguments:
    ***************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.

    ***********************
    Required Args for POST:
    ***********************

    :auto_write: bool | Whether auto_write is enabled

    *********************
    Return Object Fields:
    *********************

    :success: bool | Whether the operation was completed successfully.

    Example POST Request Data Body::

        {
        "auto_write": true
        }

    Example Successful Response from GET::

        {
          "success": true,
          "auto_write": false
        }

    Example Successful Response from POST::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Strip D9 is not initialized"
        }


    Initialize Animation:
    #####################

    URL: ``/init/animation/``

    Method(s): POST

    Details: Initialize an animation on the specified strip. Animations are dynmically imported. Sending a request
    to this endpoint will result in the animation being imported.

    **************
    Required Args:
    **************

    :strip_id: str | The strip_id that was assigned when the strip was initialized.
    :animation_id: str | The unique ID that will be used to refer to this animation in future requests.
    :animation: str | The animation type to initialize. See ``ANIMATION_CLASSES.keys()`` for possible types.
    :kwargs: dict | Dictionary of keyword arguments to pass along
      to the Animation class constructor. Different animations support different arguments. Some commonly used
      kwargs are ``color`` and ``speed``. See the LED_Animation library documentation for more
      comprehensive information.

    *********************
    Return Object Fields:
    *********************

        :success: bool | Whether the animation was initialized successfully.
        :animation_id: str | The ``animation_id`` that was assigned to the animation if it was
            successfully initialized.


    Example Request Data Body::

        {
          "strip_id" : "NEOPIXEL",
          "animation_id": "blink_builtin",
          "animation": "blink",
          "kwargs":{
            "speed": 0.25,
            "color" : "0x0000ff"
          }
        }

    Example Successful Response(s)::

        {
          "success": true,
          "animation_id": "blink_builtin"
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Invalid animation: BlinkyDiscoParty"
        }

    Start Animation:
    ################

    URL: ``/start/animation/<animation_id>/``

    Method(s): POST

    Details: Start running an animation. If the strip was in pixels mode it will be changed to animation mode.

    **********
    Path Args:
    **********

    :animation_id: str | The animation_id of the already initialized animation to start.

    *********************
    Return Object Fields:
    *********************

        :success: bool | Whether the animation was started successfully.


    Example Successful Response(s)::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Animation builtin_comet is not initialized"
        }

    Set animation property:
    #######################

    URL: ``/animation/<animation_id>/setprop``

    Method(s): POST

    Details: Set a property on the specified initialized animation. See LED_Animation docs for comprehensive info
      about which properties are supported by which aniatmions and their effects.

    **************
    Required Args:
    **************

    :name: str | The name of the property to get or set.
    :value: Any | The value to set to the property.

    *********************
    Return Object Fields:
    *********************

        :success: bool | Whether the animation property was set successfully.

    Example Request Data Body::

        {
        "name": "speed",
        "value": 0.1
        }

    Example Successful Response(s)::

        {
          "success": true
        }

    Example Error Response(s)::

        {
          "success": false,
          "error": "Invalid property highlight"
        }

    Class Methods:
    **************
    """

    # pylint: disable=too-many-statements
    def __init__(self):
        self.pool = socketpool.SocketPool(wifi.radio)
        self.server = Server(self.pool, None, debug=True)
        auths = None
        if os.getenv("HTTP_RGB_BEARER_AUTH"):
            self.auths = [
                Bearer(os.getenv("HTTP_RGB_BEARER_AUTH")),
            ]

        self.context = {
            "modes": {
                # strip_id: 'pixles' or 'animation'
            },
            "current_animations": {
                # strip_id: animation_id
            },
            "strips": {
                # "D6": neopixel_obj
            },
            "old_auto_writes": {
                # strip_id: bool
            },
            "animations": {
                # animation_id: Constructor
            },
            "animation_strip_map": {
                # animation_id : strip_id
            },
        }

        # start = time.monotonic()

        def _validate_request_data(request, required_args):
            """
            Ensure that that request data is valid JSON and contains all required arguments.
            Create Error with helpful messages for invalid cases.

            :param request: Request object with incoming data
            :param required_args: List or Tuple of strings representing required arguments.

            :return: Union[JSONResponse, dict] The dictionary containing the argument data
                or a JSONResponse Error if some of the required arguments were missing or
                invalid for other reasons.
            """
            try:
                req_obj = request.json()
            except ValueError:
                return JSONResponse(
                    request,
                    {"success": False, "error": "Invalid JSON"},
                    status=BAD_REQUEST_400,
                )

            if req_obj is None:
                return JSONResponse(
                    request,
                    {"success": False, "error": "Missing Required JSON Body"},
                    status=BAD_REQUEST_400,
                )

            missing_args = []
            for _arg in required_args:
                if _arg not in req_obj.keys():
                    missing_args.append(_arg)

            if missing_args:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Missing Required Argument(s): {missing_args}",
                    },
                    status=BAD_REQUEST_400,
                )
            return req_obj

        @self.server.route("/init/neopixels", [POST], append_slash=True)
        def init_neopixels(request: Request):
            """ """
            if self.auths is not None:
                require_authentication(request, auths)

            required_args = ("pin", "pixel_count")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            if not hasattr(board, req_data["pin"]):
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Invalid Pin: {req_data['pin']}"},
                    status=BAD_REQUEST_400,
                )

            strip_id = None
            if "id" not in req_data:
                strip_id = req_data["pin"]
            else:
                strip_id = req_data["id"]

            if strip_id in self.context["strips"]:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Strip {strip_id} is already initialized",
                    },
                    status=BAD_REQUEST_400,
                )

            _kwargs = {}
            if "kwargs" in req_data.keys():
                _kwargs = req_data["kwargs"]

            # print(_kwargs)
            try:
                _pixels = neopixel.NeoPixel(
                    getattr(board, req_data["pin"]), req_data["pixel_count"], **_kwargs
                )

                self.context["modes"][strip_id] = "pixels"

            except TypeError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": str(type_error)},
                    status=BAD_REQUEST_400,
                )
            self.context["strips"][strip_id] = _pixels

            _pixels.fill(0)
            if not _pixels.auto_write:
                _pixels.write()

            return JSONResponse(request, {"success": True, "strip_id": strip_id})

        @self.server.route("/init/dotstars", [POST], append_slash=True)
        def init_dotstars(request: Request):
            if auths is not None:
                require_authentication(request, auths)
            required_args = ("data_pin", "clock_pin", "pixel_count")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            if not hasattr(board, req_data["data_pin"]):
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Invalid Pin: {req_data['data_pin']}"},
                    status=BAD_REQUEST_400,
                )
            if not hasattr(board, req_data["clock_pin"]):
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Invalid Pin: {req_data['clock_pin']}",
                    },
                    status=BAD_REQUEST_400,
                )

            strip_id = None
            if "id" not in req_data:
                strip_id = req_data["clock_pin"] + req_data["data_pin"]
            else:
                strip_id = req_data["id"]

            if strip_id in self.context["strips"]:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Strip {strip_id} is already initialized",
                    },
                    status=BAD_REQUEST_400,
                )

            _kwargs = {}
            if "kwargs" in req_data.keys():
                _kwargs = req_data["kwargs"]

            # print(_kwargs)
            try:
                _pixels = dotstar.DotStar(
                    getattr(board, req_data["clock_pin"]),
                    getattr(board, req_data["data_pin"]),
                    req_data["pixel_count"],
                    **_kwargs,
                )

                self.context["modes"][strip_id] = "pixels"
            except TypeError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "TypeError: ": str(type_error)},
                    status=BAD_REQUEST_400,
                )
            except ValueError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "Value Error: ": str(type_error)},
                    status=BAD_REQUEST_400,
                )
            self.context["strips"][strip_id] = _pixels

            _pixels.fill(0)
            if not _pixels.auto_write:
                _pixels.write()

            return JSONResponse(request, {"success": True, "strip_id": strip_id})

        # pylint: disable=inconsistent-return-statements
        @self.server.route("/pixels/<strip_id>", [POST, GET], append_slash=True)
        def pixels(request: Request, strip_id):
            if auths is not None:
                require_authentication(request, auths)
            if request.method == POST:
                if strip_id not in self.context["strips"]:
                    return JSONResponse(
                        request,
                        {
                            "success": False,
                            "error": f"Strip {strip_id} is not initialized",
                        },
                        status=BAD_REQUEST_400,
                    )
                required_args = ("pixels",)
                error_resp_or_req_data = _validate_request_data(request, required_args)
                if isinstance(error_resp_or_req_data, JSONResponse):
                    return error_resp_or_req_data
                req_data = error_resp_or_req_data

                _pixels_input_data = req_data["pixels"]

                if not isinstance(_pixels_input_data, (dict)):
                    return JSONResponse(
                        request,
                        {
                            "success": False,
                            "error": "Pixels must be list or dictionary",
                        },
                    )

                if "blank_pixels" in req_data.keys():
                    if req_data["blank_pixels"] is True:
                        self.context["strips"][strip_id].fill(0x0)
                        self.context["strips"][strip_id].write()

                # if self.context['mode'] != 'pixels':
                #     self.context['mode'] = 'pixels'

                if self.context["modes"][strip_id] != "pixels":
                    self.context["modes"][strip_id] = "pixels"
                    print(
                        f"setting {strip_id}.auto_write = {self.context['old_auto_writes'][strip_id]}"
                    )
                    self.context["strips"][strip_id].auto_write = self.context[
                        "old_auto_writes"
                    ][strip_id]

                _cur_key = None
                try:
                    for key in req_data["pixels"].keys():
                        _cur_key = key
                        _cur_value = req_data["pixels"][key]

                        try:
                            self.context["strips"][strip_id][
                                int(key)
                            ] = convert_color_to_num(_cur_value)
                        except ValueError as value_error:
                            return JSONResponse(
                                request,
                                {
                                    "success": False,
                                    "error": f"Value Error from '{_cur_value}': {str(value_error)}",
                                },
                            )

                except IndexError:
                    return JSONResponse(
                        request,
                        {"success": False, "error": f"Index Error on Key: {_cur_key}"},
                        status=BAD_REQUEST_400,
                    )

                return JSONResponse(request, {"success": True})

            if request.method == GET:
                if strip_id not in self.context["strips"]:
                    return JSONResponse(
                        request,
                        {
                            "success": False,
                            "error": f"Strip {strip_id} is not initialized",
                        },
                        status=BAD_REQUEST_400,
                    )

                _color_type = request.query_params.get("color_type") or "rgb"

                _strip_colors = {}

                for i in range(len(self.context["strips"][strip_id])):
                    if _color_type == "rgb":
                        _strip_colors[i] = self.context["strips"][strip_id][i]
                    elif _color_type == "hex":
                        _strip_colors[i] = hex(
                            rgb_to_hex(self.context["strips"][strip_id][i])
                        )

                return JSONResponse(request, {"success": True, "pixels": _strip_colors})

        @self.server.route("/write/<strip_id>", [POST], append_slash=True)
        def write(request: Request, strip_id):
            if auths is not None:
                require_authentication(request, auths)
            if strip_id not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )
            self.context["strips"][strip_id].write()
            return JSONResponse(request, {"success": True})

        @self.server.route("/fill/<strip_id>", [POST], append_slash=True)
        def fill(request: Request, strip_id):
            if auths is not None:
                require_authentication(request, auths)
            if strip_id not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )
            required_args = ("color",)
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data
            if self.context["mode"] != "pixels":
                self.context["mode"] = "pixels"
                print(
                    f"setting {strip_id}.auto_write = {self.context['old_auto_writes'][strip_id]}"
                )
                self.context["strips"][strip_id].auto_write = self.context[
                    "old_auto_writes"
                ][strip_id]

            self.context["strips"][strip_id].fill(
                convert_color_to_num(req_data["color"])
            )
            return JSONResponse(request, {"success": True})

        @self.server.route("/brightness/<strip_id>", [GET, POST], append_slash=True)
        def brightness(request: Request, strip_id):
            if auths is not None:
                require_authentication(request, auths)
            if strip_id not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )

            if request.method == POST:
                required_args = ("brightness",)
                error_resp_or_req_data = _validate_request_data(request, required_args)
                if isinstance(error_resp_or_req_data, JSONResponse):
                    return error_resp_or_req_data
                req_data = error_resp_or_req_data
                self.context["strips"][strip_id].brightness = req_data["brightness"]
                return JSONResponse(request, {"success": True})

            if request.method == GET:
                return JSONResponse(
                    request,
                    {
                        "success": True,
                        "brightness": self.context["strips"][strip_id].brightness,
                    },
                )

        @self.server.route("/auto_write/<strip_id>", [GET, POST], append_slash=True)
        def auto_write(request: Request, strip_id):
            if auths is not None:
                require_authentication(request, auths)
            if strip_id not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )

            if request.method == POST:
                required_args = ("auto_write",)
                error_resp_or_req_data = _validate_request_data(request, required_args)
                if isinstance(error_resp_or_req_data, JSONResponse):
                    return error_resp_or_req_data
                req_data = error_resp_or_req_data
                self.context["strips"][strip_id].auto_write = req_data["auto_write"]
                return JSONResponse(request, {"success": True})

            if request.method == GET:
                return JSONResponse(
                    request,
                    {
                        "success": True,
                        "auto_write": self.context["strips"][strip_id].auto_write,
                    },
                )

        @self.server.route("/init/animation", [POST], append_slash=True)
        def init_animation(request: Request):
            if auths is not None:
                require_authentication(request, auths)

            required_args = ("strip_id", "animation_id", "animation", "kwargs")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            strip_id = req_data["strip_id"]
            if req_data["strip_id"] not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )

            if req_data["animation"] not in ANIMATION_CLASSES:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Animation {req_data['animation']} is unknown.",
                    },
                    status=BAD_REQUEST_400,
                )

            if req_data["animation_id"] in self.context["animations"]:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Animation {req_data['animation_id']} already exists.",
                    },
                    status=BAD_REQUEST_400,
                )

            _kwargs = {}
            if "kwargs" in req_data.keys():
                _kwargs = req_data["kwargs"]

            # if "color" not in _kwargs:
            #     return JSONResponse(request, {"success": False, "error": f"Missing required argument color"},
            #                         status=BAD_REQUEST_400)

            _color = None
            if "color" in _kwargs.keys():
                _color = convert_color_to_num(_kwargs["color"])
                del _kwargs["color"]

            animation_id = req_data["animation_id"]

            self.context["old_auto_writes"][strip_id] = self.context["strips"][
                strip_id
            ].auto_write

            anim_constructor = import_animation_contructor(req_data["animation"])
            if anim_constructor is None:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Invalid animation: {req_data['animation']}",
                    },
                    status=BAD_REQUEST_400,
                )

            if _color:
                self.context["animations"][animation_id] = anim_constructor(
                    self.context["strips"][strip_id], color=_color, **_kwargs
                )
            else:
                self.context["animations"][animation_id] = anim_constructor(
                    self.context["strips"][strip_id], **_kwargs
                )
            self.context["animation_strip_map"][req_data["animation_id"]] = strip_id

            print(self.context["animations"][req_data["animation_id"]])

            return JSONResponse(
                request, {"success": True, "animation_id": req_data["animation_id"]}
            )

        @self.server.route("/start/animation/<animation_id>", [POST], append_slash=True)
        def start_animation(request: Request, animation_id):
            if auths is not None:
                require_authentication(request, auths)

            if animation_id not in self.context["animations"]:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Animation {animation_id} is not initialized",
                    },
                    status=BAD_REQUEST_400,
                )

            # self.context['current_animation'] = animation_id
            self.context["current_animations"][
                self.context["animation_strip_map"][animation_id]
            ] = animation_id
            # self.context['mode'] = 'animation'
            self.context["modes"][
                self.context["animation_strip_map"][animation_id]
            ] = "animation"
            return JSONResponse(request, {"success": True})

        @self.server.route(
            "/animation/<animation_id>/setprop", [POST], append_slash=True
        )
        def animation_setprop(request: Request, animation_id):
            if auths is not None:
                require_authentication(request, auths)

            if animation_id not in self.context["animations"]:
                return JSONResponse(
                    request,
                    {
                        "success": False,
                        "error": f"Animation {animation_id} is not initialized",
                    },
                    status=BAD_REQUEST_400,
                )

            required_args = ("name", "value")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            if hasattr(self.context["animations"][animation_id], req_data["name"]):
                setattr(
                    self.context["animations"][animation_id],
                    req_data["name"],
                    req_data["value"],
                )
            else:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Invalid property {req_data['name']}"},
                    status=BAD_REQUEST_400,
                )

            return JSONResponse(request, {"success": True})

        self.server.start(str(wifi.radio.ipv4_address))

    def animate(self):
        """
        Process one frame of animation for all animations that are
        currently running.

        Should be called frequently from the main loop.

        :return: None
        """
        for strip_id in self.context["modes"]:
            if self.context["modes"][strip_id] == "animation":
                self.context["animations"][
                    self.context["current_animations"][strip_id]
                ].animate()

    def poll(self):
        """
        Process http server polling to handle any requests that have come in.
        Should be called frequently from the main loop.

        :return: None
        """
        self.server.poll()


# while True:
#
#     # animations.animate()
#
#     for strip_id in context['modes'].keys():
#         if context['modes'][strip_id] == 'animation':
#             context['animations'][context["current_animations"][strip_id]].animate()
#     # if context["mode"] == "animation":
#     # context['animations'][context["current_animation"]].animate()
#
#     try:
#         # Do something useful in this section,
#         # for example read a sensor and capture an average,
#         # or a running total of the last 10 samples
#
#         # Process any waiting requests
#         server.poll()
#
#         # If you want you can stop the server by calling server.stop() anywhere in your code
#     except OSError as error:
#         print(error)
#         continue
