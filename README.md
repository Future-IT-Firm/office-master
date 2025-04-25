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


## TODO

- [ ] /get_storage_dir
- [ ] /flush users.txt, group.txt, data.txt #bot level clearation(data mount)
- [ ] /flush_all users.txt, group.txt, data.txt, storage_dir #system level creation (shared mount+data mount)