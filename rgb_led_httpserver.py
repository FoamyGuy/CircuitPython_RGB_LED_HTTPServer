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

try:
    import neopixel
except ImportError:
    print("WARNING: neopixel import not found")
try:
    import adafruit_dotstar as dotstar
except ImportError:
    print("WARNING: adafruit_dotstar import not found")
import socketpool
import wifi
from adafruit_httpserver import (
    Server,
    Request,
    JSONResponse,
    POST,
    BAD_REQUEST_400,
    INTERNAL_SERVER_ERROR_500,
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
    "pulse": ("adafruit_led_animation.animation.pulse", "Pulse"),
    "chase": ("adafruit_led_animation.animation.chase", "Chase"),
    "customcolorchase": (
        "adafruit_led_animation.animation.customcolorchase",
        "CustomColorChase",
    ),
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


def convert_color_list(color_str_list: list):
    """
    Convert a list of string colors into numbers ready to be passed to the pixel object.

    :param color_str_list List[str...]: List of strings representing hex colors
    :return List[int]: The List of converted colors ready to be passed to pixel object
    """
    output_list = []
    for color_str in color_str_list:
        output_list.append(convert_color_to_num(color_str))
    return output_list


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

    """

    # pylint: disable=too-many-statements
    def __init__(self, startup_actions: dict = None):
        self.pool = socketpool.SocketPool(wifi.radio)
        self.server = Server(self.pool, None, debug=True)
        self.auths = None
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

        if startup_actions:
            self._process_startup_actions(startup_actions)

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
                require_authentication(request, self.auths)

            required_args = ("pin", "pixel_count")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            try:
                result = self._process_init_neopixels(req_data)
                return JSONResponse(request, result)
            except ValueError as value_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"ValueError: {value_error}"},
                    status=BAD_REQUEST_400,
                )
            except TypeError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"TypeError: {type_error}"},
                    status=BAD_REQUEST_400,
                )

        @self.server.route("/init/dotstars", [POST], append_slash=True)
        def init_dotstars(request: Request):
            if self.auths is not None:
                require_authentication(request, self.auths)
            required_args = ("data_pin", "clock_pin", "pixel_count")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            try:
                result = self._process_init_dotstars(req_data)
                return JSONResponse(request, result)
            except ValueError as value_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"ValueError: {value_error}"},
                    status=BAD_REQUEST_400,
                )
            except TypeError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"TypeError: {type_error}"},
                    status=BAD_REQUEST_400,
                )

        # pylint: disable=inconsistent-return-statements
        @self.server.route("/pixels/<strip_id>", [POST, GET], append_slash=True)
        def pixels(request: Request, strip_id):
            if self.auths is not None:
                require_authentication(request, self.auths)
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
                        self.context["strips"][strip_id].show()

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

        @self.server.route("/show/<strip_id>", [POST], append_slash=True)
        def show(request: Request, strip_id):
            if self.auths is not None:
                require_authentication(request, self.auths)
            if strip_id not in self.context["strips"]:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Strip {strip_id} is not initialized"},
                    status=BAD_REQUEST_400,
                )
            self.context["strips"][strip_id].show()
            return JSONResponse(request, {"success": True})

        @self.server.route("/fill/<strip_id>", [POST], append_slash=True)
        def fill(request: Request, strip_id):
            if self.auths is not None:
                require_authentication(request, self.auths)
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
            if self.context["modes"][strip_id] != "pixels":
                self.context["modes"][strip_id] = "pixels"
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
            if self.auths is not None:
                require_authentication(request, self.auths)
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
            if self.auths is not None:
                require_authentication(request, self.auths)
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
            if self.auths is not None:
                require_authentication(request, self.auths)

            required_args = ("strip_id", "animation_id", "animation", "kwargs")
            error_resp_or_req_data = _validate_request_data(request, required_args)
            if isinstance(error_resp_or_req_data, JSONResponse):
                return error_resp_or_req_data
            req_data = error_resp_or_req_data

            try:
                result = self._process_init_animation(req_data)
                return JSONResponse(request, result)
            except ValueError as value_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"ValueError: {value_error}"},
                    status=BAD_REQUEST_400,
                )
            except TypeError as type_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"TypeError: {type_error}"},
                    status=BAD_REQUEST_400,
                )
            except ImportError as import_error:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"ImportError: {import_error}"},
                    status=INTERNAL_SERVER_ERROR_500,
                )

        @self.server.route("/start/animation/<animation_id>", [POST], append_slash=True)
        def start_animation(request: Request, animation_id):
            if self.auths is not None:
                require_authentication(request, self.auths)

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
            if self.auths is not None:
                require_authentication(request, self.auths)

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

            _value = req_data["value"]

            if "colors" in req_data["name"]:
                _value = convert_color_list(req_data["value"])
            elif "color" in req_data["name"]:
                _value = convert_color_to_num(req_data["value"])

            if hasattr(self.context["animations"][animation_id], req_data["name"]):
                setattr(
                    self.context["animations"][animation_id], req_data["name"], _value
                )
            else:
                return JSONResponse(
                    request,
                    {"success": False, "error": f"Invalid property {req_data['name']}"},
                    status=BAD_REQUEST_400,
                )

            return JSONResponse(request, {"success": True})

        self.server.start(str(wifi.radio.ipv4_address))

    def _process_init_neopixels(self, req_data_obj):
        if not hasattr(board, req_data_obj["pin"]):
            raise ValueError(f"Invalid Pin: {req_data_obj['pin']}")

        strip_id = None
        if "id" not in req_data_obj:
            strip_id = req_data_obj["pin"]
        else:
            strip_id = req_data_obj["id"]

        if strip_id in self.context["strips"]:
            raise ValueError(f"Strip {strip_id} is already initialized")

        _kwargs = {}
        if "kwargs" in req_data_obj.keys():
            _kwargs = req_data_obj["kwargs"]

        # print(_kwargs)
        try:
            _pixels = neopixel.NeoPixel(
                getattr(board, req_data_obj["pin"]),
                req_data_obj["pixel_count"],
                **_kwargs,
            )

            self.context["modes"][strip_id] = "pixels"

            self.context["strips"][strip_id] = _pixels

            _pixels.fill(0)
            if not _pixels.auto_write:
                _pixels.show()

        except TypeError as type_error:
            raise type_error

        return {"success": True, "strip_id": strip_id}

    def _process_init_dotstars(self, req_data_obj):
        if not hasattr(board, req_data_obj["data_pin"]):
            raise ValueError(f"Invalid Pin: {req_data_obj['data_pin']}")

        if not hasattr(board, req_data_obj["clock_pin"]):
            raise ValueError(f"Invalid Pin: {req_data_obj['clock_pin']}")

        strip_id = None
        if "id" not in req_data_obj:
            strip_id = req_data_obj["clock_pin"] + req_data_obj["data_pin"]
        else:
            strip_id = req_data_obj["id"]

        if strip_id in self.context["strips"]:
            raise ValueError(f"Strip {strip_id} is already initialized")

        _kwargs = {}
        if "kwargs" in req_data_obj.keys():
            _kwargs = req_data_obj["kwargs"]

        # print(_kwargs)
        try:
            _pixels = dotstar.DotStar(
                getattr(board, req_data_obj["clock_pin"]),
                getattr(board, req_data_obj["data_pin"]),
                req_data_obj["pixel_count"],
                **_kwargs,
            )

            self.context["modes"][strip_id] = "pixels"

            self.context["strips"][strip_id] = _pixels

            _pixels.fill(0)
            if not _pixels.auto_write:
                _pixels.show()

            return {"success": True, "strip_id": strip_id}

        except TypeError as type_error:
            raise type_error

        except ValueError as value_error:
            raise value_error

    def _process_init_animation(self, req_data_obj):
        strip_id = req_data_obj["strip_id"]
        if req_data_obj["strip_id"] not in self.context["strips"]:
            raise ValueError(f"Strip {strip_id} is not initialized")

        if req_data_obj["animation"] not in ANIMATION_CLASSES:
            raise ValueError(f"Animation {req_data_obj['animation']} is unknown.")

        if req_data_obj["animation_id"] in self.context["animations"]:
            raise ValueError(
                f"Animation {req_data_obj['animation_id']} already exists."
            )

        _kwargs = {}
        if "kwargs" in req_data_obj.keys():
            _kwargs = req_data_obj["kwargs"]

        if "color" in _kwargs.keys():
            _kwargs["color"] = convert_color_to_num(_kwargs["color"])
        if "colors" in _kwargs.keys():
            _kwargs["colors"] = convert_color_list(_kwargs["colors"])

        animation_id = req_data_obj["animation_id"]

        self.context["old_auto_writes"][strip_id] = self.context["strips"][
            strip_id
        ].auto_write

        try:
            anim_constructor = import_animation_contructor(req_data_obj["animation"])
        except ImportError as import_error:
            raise import_error

        if anim_constructor is None:
            raise ValueError(f"Invalid animation: {req_data_obj['animation']}")

        try:
            self.context["animations"][animation_id] = anim_constructor(
                self.context["strips"][strip_id], **_kwargs
            )

            self.context["animation_strip_map"][req_data_obj["animation_id"]] = strip_id

            # print(self.context["animations"][req_data["animation_id"]])

            if "start" in req_data_obj.keys():
                if req_data_obj["start"]:
                    self.context["current_animations"][
                        self.context["animation_strip_map"][animation_id]
                    ] = animation_id
                    # self.context['mode'] = 'animation'
                    self.context["modes"][
                        self.context["animation_strip_map"][animation_id]
                    ] = "animation"

            return {"success": True, "animation_id": req_data_obj["animation_id"]}

        except TypeError as type_error:
            raise type_error

    def _process_startup_actions(self, actions_obj):
        """
        Optionally initialize rgb strips and animations automatically
        when the server is initialized.

        :param actions_obj: A dictionary of start actions to perform.
            valid keys are "init_neopixels", "init_dotstars", "init_animations"
            all others will be ignored.
        :return: None
        """

        if "init_neopixels" in actions_obj.keys():
            for _init_pixels_obj in actions_obj["init_neopixels"]:
                try:
                    self._process_init_neopixels(_init_pixels_obj)
                except ValueError as value_error:
                    print(f"ValueError during startup action: {value_error}")
                    print(f"action: {_init_pixels_obj}")
                except TypeError as type_error:
                    print(f"TypeError during startup action: {type_error}")
                    print(f"action: {_init_pixels_obj}")

        if "init_dotstars" in actions_obj.keys():
            for _init_dotstars_obj in actions_obj["init_dotstars"]:
                try:
                    self._process_init_dotstars(_init_dotstars_obj)
                except ValueError as value_error:
                    print(f"ValueError during startup action: {value_error}")
                    print(f"action: {_init_dotstars_obj}")
                except TypeError as type_error:
                    print(f"TypeError during startup action: {type_error}")
                    print(f"action: {_init_dotstars_obj}")

        if "init_animations" in actions_obj.keys():
            for _init_animation_obj in actions_obj["init_animations"]:
                try:
                    self._process_init_animation(_init_animation_obj)
                except ValueError as value_error:
                    print(f"ValueError during startup action: {value_error}")
                    print(f"action: {_init_animation_obj}")
                except TypeError as type_error:
                    print(f"TypeError during startup action: {type_error}")
                    print(f"action: {_init_animation_obj}")

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
