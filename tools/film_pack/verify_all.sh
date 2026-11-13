#!/usr/bin/env bash
cd /mnt/d/0_Project/01Test/ep5-fw-reverse
for key in gold200 portra160 velvia50 classicchrome ektar100 bleach moriyama_bw trix_bw; do
  echo "=== $key ==="
  PYTHONPATH=. python3 tools/film_pack/verify_film.py "$key" 2>&1 | grep -aE 'changed modes|match generated|movie82 rerouted|VERIFY'
done
