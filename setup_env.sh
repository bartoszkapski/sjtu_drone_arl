#!/bin/bash

pip3 install --upgrade pip
pip3 install -r requirements.txt
cd ..

colcon build --symlink-install
