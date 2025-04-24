```
sudo ip link add link enp10s0 name enp10s0.10 type vlan id 10
sudo ip addr add 192.168.100.1/24 dev enp10s0.10
sudo ip link set enp10s0.10 up


```

```
NETWORK_DRIVER=bridge
PARENT_INTERFACE=wlan0

OFFICE_HELPER_IP=172.20.0.11
OFFICE_HELPER_MAC=02:42:ac:14:00:0b

OFFICETESTER_IP=172.20.0.12
OFFICETESTER_MAC=02:42:ac:14:00:0c

```


