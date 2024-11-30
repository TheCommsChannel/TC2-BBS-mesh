#!/bin/sh
if [ ! -f "/config/config.ini" ]; then
    cp "/TC2-BBS-mesh/example_config.ini" "/config/config.ini"
fi
if [ ! -f "/config/fortunes.txt" ]; then
    cp "/TC2-BBS-mesh/fortunes.txt" "/config/fortunes.txt"
fi
