# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: MIT
import requests

ip_address = "192.168.1.227"

strip_id = "D13D11"

# headers = {"Authorization": f"Bearer {os.getenv('HTTP_RGB_BEARER_AUTH')}"}
headers = {"Authorization": "Bearer cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk"}
data_obj = {"brightness": 0.03}
resp = requests.post(
    f"http://{ip_address}/brightness/{strip_id}/", headers=headers, json=data_obj
)

print(resp.status_code)
print(resp.json())
