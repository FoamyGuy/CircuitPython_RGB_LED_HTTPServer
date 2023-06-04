# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: MIT
import requests

ip_address = "192.168.1.227"
animation_id = "D13D11_Comet"

# print(os.getenv("HTTP_RGB_BEARER_AUTH"))
# headers = {"Authorization": f"Bearer {os.getenv('HTTP_RGB_BEARER_AUTH')}"}
headers = {"Authorization": "Bearer cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk"}

resp = requests.post(
    f"http://{ip_address}/start/animation/{animation_id}/", headers=headers
)

# print(resp.status_code)
if resp.status_code == 200:
    try:
        print(resp.json())
    except requests.exceptions.JSONDecodeError:
        print("JSON Error")
        print(resp.content)
else:
    print(f"Error Response: {resp.status_code}")
    print(resp.content)
