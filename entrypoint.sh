#!/bin/bash
set -e

CONFIG_DIR=/app/config
CONFIG_FILE=$CONFIG_DIR/config.ini
SAMPLE_FILE=config.ini.sample

# Create the config directory if it does not exist
mkdir -p $CONFIG_DIR

# Check if the config file exists, if not, copy the sample file
if [ ! -f $CONFIG_FILE ]; then
    if [ -f $SAMPLE_FILE ]; then
        cp $SAMPLE_FILE $CONFIG_FILE
        echo "Copied $SAMPLE_FILE to $CONFIG_FILE"
    else
        echo "Sample file $SAMPLE_FILE does not exist. Please provide a sample file."
    fi
else
    echo "Config file $CONFIG_FILE already exists."
fi

exec "$@"
