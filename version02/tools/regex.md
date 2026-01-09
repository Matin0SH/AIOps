# Regex Catalog

## get_interface_brief
Used by `Collector.get_interface_brief` to parse `show ip interface brief`.

```regex
^(?P<interface>\S+)\s+(?P<ip_address>\S+)\s+(?P<ok>\S+)\s+(?P<method>\S+)\s+(?P<status>.+?)\s+(?P<protocol>\S+)\s*$
```

## get_cdp_neighbors
Used by `Collector.get_cdp_neighbors` to parse `show cdp neighbors detail`.

```regex split
-{20,}|(?=Device ID:)
```

```regex device
Device ID:\s*(\S+)
```

```regex ip
IP address:\s*(\d+\.\d+\.\d+\.\d+)
```

```regex platform
Platform:\s*([^,]+),\s*Capabilities:\s*(.+)
```

```regex interface
Interface:\s*(\S+),\s*Port ID \(outgoing port\):\s*(\S+)
```

## get_ospf_neighbors
Used by `Collector.get_ospf_neighbors` to parse `show ip ospf neighbor`.

```regex
^(?P<neighbor_id>\d+\.\d+\.\d+\.\d+)\s+(?P<priority>\d+)\s+(?P<state>\S+)\s+(?P<dead_time>\S+)\s+(?P<address>\d+\.\d+\.\d+\.\d+)\s+(?P<interface>\S+)\s*$
```

## get_vlan_brief
Used by `Collector.get_vlan_brief` to parse `show vlan brief`.

```regex
^(?P<vlan_id>\d+)\s+(?P<name>\S+)\s+(?P<status>\S+)\s*(?P<ports>.*)$
```

## get_trunk_interfaces
Used by `Collector.get_trunk_interfaces` to parse `show interfaces trunk`.

```regex config
^(?P<port>\S+)\s+(?P<mode>\S+)\s+(?P<encapsulation>\S+)\s+(?P<status>\S+)\s+(?P<native_vlan>\S+)\s*$
```

```regex vlans
^(?P<port>\S+)\s+(?P<vlans>.*)$
```

## get_mac_address_table
Used by `Collector.get_mac_address_table` to parse `show mac address-table`.

```regex
^\s*(?P<vlan>\d+)\s+(?P<mac_address>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+(?P<type>\S+)\s+(?P<port>\S+)\s*$
```

## get_spanning_tree_summary
Used by `Collector.get_spanning_tree_summary` to parse `show spanning-tree summary`.

```regex mode
Switch is in (\S+) mode
```

```regex root_bridge
Root bridge for:\s+(.+)
```

```regex extended_system_id
Extended system ID\s+is (\S+)
```

```regex portfast_default
Portfast Default\s+is (\S+)
```

```regex portfast_bpdu_guard
Portfast Edge BPDU Guard Default\s+is (\S+)
```

```regex portfast_bpdu_filter
Portfast Edge BPDU Filter Default\s+is (\S+)
```

```regex loopguard
Loopguard Default\s+is (\S+)
```

```regex bridge_assurance
Bridge Assurance\s+is (\S+)
```

```regex etherchannel_misconfig
EtherChannel misconfig guard\s+is (\S+)
```

```regex pathcost
Configured Pathcost method used is (\S+)
```

```regex uplinkfast
UplinkFast\s+is (\S+)
```

```regex backbonefast
BackboneFast\s+is (\S+)
```

```regex vlan_stats
^(?P<vlan>VLAN\d+)\s+(?P<blocking>\d+)\s+(?P<listening>\d+)\s+(?P<learning>\d+)\s+(?P<forwarding>\d+)\s+(?P<stp_active>\d+)\s*$
```
