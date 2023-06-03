# SPDX-FileCopyrightText: Copyright (c) 2023 Tim C
#
# SPDX-License-Identifier: MIT
import os
import requests

ip_address = "192.168.1.227"

strip_id = "D6"

headers = {"Authorization": f"Bearer {os.getenv('HTTP_RGB_BEARER_AUTH')}"}
data_obj = {"color": "0xff00ff"}
resp = requests.post(
    f"http://{ip_address}/fill/{strip_id}/", headers=headers, json=data_obj
)

print(resp.status_code)
print(resp.json())
