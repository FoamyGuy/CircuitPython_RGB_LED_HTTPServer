# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: MIT
import os
import requests

ip_address = "192.168.1.227"
#print(os.getenv("HTTP_RGB_BEARER_AUTH"))
#headers = {"Authorization": f"Bearer {os.getenv('HTTP_RGB_BEARER_AUTH')}"}
headers = {"Authorization": f"Bearer cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk"}
data_obj = {
    "clock_pin": "D13",
    "data_pin": "D10",
    "pixel_count": 6*12,
    "kwargs": {"brightness": 0.01, "auto_write": True},
}
resp = requests.post(
    f"http://{ip_address}/init/dotstars/", headers=headers, json=data_obj
)

print(resp.status_code)
print(resp.json())
