#!/bin/sh
if [ ! -f "/config/config.ini" ]; then
    cp "/TC2-BBS-mesh/config.ini" "/config/config.ini"
fi