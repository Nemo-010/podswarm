#!/bin/bash
# run.sh N server_prefix threads hbms
N=$1; pre=$2; th=$3; hb=$4
port=$((30000 + RANDOM % 20000))
setsid $pre ./target/release/conn server --port $port --threads $th $5 > srv_$N.txt 2>&1 < /dev/null &
sp=$!
sleep 3
taskset -c 4-7 ./target/release/conn client --port $port --n $N --hb-ms $hb --secs 14 --threads 4 2>&1 | tee cli_$N.txt
kill $sp 2>/dev/null
tail -4 srv_$N.txt
