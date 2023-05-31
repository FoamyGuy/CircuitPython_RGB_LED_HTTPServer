# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: Unlicense
from rgb_led_httpserver import RGBLedServer

server_process = RGBLedServer()

while True:
    server_process.animate()
    server_process.poll()