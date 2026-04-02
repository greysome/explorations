#!/bin/bash
for file in $(find /usr/include -type f); do
  ./status-set "Reading $file..."
  while read p; do
    echo "$p"
    sleep 0.0005
  done <$file
done