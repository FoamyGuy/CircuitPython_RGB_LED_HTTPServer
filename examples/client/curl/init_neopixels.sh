curl -X POST --location "http://192.168.1.227/init/neopixels/" \
    -H "Authorization: Bearer cIgw2mX7Ditmxu2i8kD0EaeARLbsKnPmAwbxDc7gWDk" \
    -d @- << EOF
{
    "pin": "D6",
    "pixel_count": 32,
    "kwargs": {
        "brightness": 0.01,
        "bpp": 3,
        "auto_write": true
    }
}
EOF