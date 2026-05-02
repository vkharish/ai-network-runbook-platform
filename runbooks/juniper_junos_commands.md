# Juniper JunOS Command Reference Runbook

## Overview

This runbook is a quick-reference for Juniper JunOS CLI commands used during network incident diagnosis on MX, PTX, QFX, and vMX platforms. JunOS has a hierarchical configuration model and operational/configuration mode separation.

---

## 1. JunOS Key Concepts

| Concept | Description |
|---------|-------------|
| Operational mode | `>` prompt — show commands, monitoring |
| Configuration mode | `#` prompt — edit and commit config |
| Commit model | Changes staged in candidate config, activated by `commit` |
| Rollback | `rollback <number>` to revert to previous config |
| Unified CLI | Same CLI across all Juniper platforms |

---

## 2. Configuration Workflow

```
# Enter configuration mode
configure
configure exclusive    # lock config from other users

# Navigate hierarchy
edit protocols bgp
edit interfaces ge-0/0/0

# Show candidate changes
show | compare    # diff between candidate and active config

# Commit configuration
commit
commit confirmed 5    # auto-rollback in 5 minutes if not confirmed again

# Rollback
rollback 0    # rollback to last committed config
rollback 1    # rollback to config before last commit
rollback ?    # show available rollback points

# Exit config mode
exit
quit

# Exit without committing
exit discard
```

---

## 3. BGP Commands (JunOS)

```
# Show BGP summary
show bgp summary
show bgp summary instance <routing-instance>

# Show neighbor detail
show bgp neighbor
show bgp neighbor <peer-ip>
show bgp neighbor <peer-ip> | match State|prefix|hold

# Show received/advertised routes
show route receive-protocol bgp <peer-ip>
show route advertising-protocol bgp <peer-ip>
show route protocol bgp

# Show specific prefix
show route 10.0.0.0/8
show route 10.0.0.1/32 detail

# Clear BGP session
clear bgp neighbor <peer-ip>
clear bgp neighbor <peer-ip> soft
clear bgp neighbor all

# Damping information
show bgp neighbor <peer-ip> flap-statistics
clear bgp flap-statistics
```

---

## 4. OSPF Commands (JunOS)

```
# Show OSPF neighbors
show ospf neighbor
show ospf neighbor detail
show ospf neighbor extensive

# Show OSPF database
show ospf database
show ospf database detail
show ospf database router detail
show ospf database summary

# Show OSPF interface
show ospf interface
show ospf interface detail
show ospf interface brief

# Show OSPF statistics
show ospf statistics

# Show OSPF routes
show route protocol ospf

# Clear OSPF (drops all adjacencies — use with caution)
clear ospf neighbor all
clear ospf database purge all

# Restart OSPF process
restart ospf
```

---

## 5. IS-IS Commands (JunOS)

```
# Show IS-IS adjacency
show isis adjacency
show isis adjacency detail

# Show IS-IS database
show isis database
show isis database detail

# Show IS-IS interface
show isis interface
show isis interface detail

# Show IS-IS routes
show isis route
show route protocol isis

# Show IS-IS statistics
show isis statistics

# Show IS-IS SPF
show isis spf brief
show isis spf detail

# Clear IS-IS session
clear isis adjacency all
clear isis database
```

---

## 6. Interface Commands (JunOS)

```
# Show interface status
show interfaces
show interfaces terse          # brief table format — best for quick overview
show interfaces ge-0/0/0
show interfaces ge-0/0/0 detail
show interfaces ge-0/0/0 extensive    # includes error counters and statistics

# Show interface statistics
show interfaces ge-0/0/0 statistics

# Show physical layer (optical)
show interfaces ge-0/0/0 diagnostics optics    # optical power levels
show chassis hardware                           # SFP/QSFP inventory

# Show interface errors
show interfaces ge-0/0/0 | match error|drop|CRC

# Clear interface statistics
clear interfaces statistics ge-0/0/0
clear interfaces statistics all

# Bring interface up/down (in config mode)
set interfaces ge-0/0/0 disable    # administratively down
delete interfaces ge-0/0/0 disable # bring back up
commit
```

---

## 7. Routing Table Commands (JunOS)

```
# Show routing table
show route
show route table inet.0           # IPv4 unicast
show route table inet6.0          # IPv6 unicast
show route table mpls.0           # MPLS

# Show specific prefix
show route 10.0.0.1/32
show route 10.0.0.1/32 detail
show route 10.0.0.1/32 extensive

# Show routes by protocol
show route protocol bgp
show route protocol ospf
show route protocol isis
show route protocol static
show route protocol direct

# Show forwarding table (active routes only)
show route forwarding-table
show route forwarding-table destination 10.0.0.1/32

# Show route summary
show route summary

# Routing instance (VRF equivalent)
show route table <instance-name>.inet.0
```

---

## 8. MPLS / LDP Commands (JunOS)

```
# Show LDP session
show ldp session
show ldp session detail

# Show LDP neighbors
show ldp neighbor

# Show LDP database (label bindings)
show ldp database
show ldp database session <peer-ip>

# Show LDP interface
show ldp interface

# Show MPLS LSP
show mpls lsp
show mpls lsp extensive
show mpls lsp name <lsp-name>

# Show RSVP
show rsvp session
show rsvp neighbor

# Show MPLS route table
show route table mpls.0

# Clear LDP
clear ldp session
clear ldp statistics
```

---

## 9. System Health Commands (JunOS)

```
# Show chassis information
show chassis hardware
show chassis routing-engine
show chassis fpc
show chassis environment
show chassis environment routing-engine
show chassis environment fpc

# Show system processes
show system processes
show system processes extensive | match cpu    # top CPU consumers

# Show system resources
show system statistics
show system memory

# Show system log
show log messages
show log messages | last 100
show log messages | match BGP|OSPF|ISIS|ERROR|WARN
show log chassisd    # hardware/chassis messages

# Show version
show version
show version detail

# Show uptime
show system uptime

# Show alarms
show chassis alarms
show system alarms
```

---

## 10. Firewall Filter (ACL) Commands (JunOS)

```
# Show filter counters
show firewall
show firewall filter <filter-name>
show firewall filter <filter-name> counter

# Show filter detail
show firewall filter <filter-name> detail

# Clear filter counters
clear firewall filter <filter-name>
```

---

## 11. Class of Service (QoS) Commands (JunOS)

```
# Show CoS configuration
show class-of-service
show class-of-service interface ge-0/0/0
show class-of-service interface ge-0/0/0 detail

# Show queue statistics
show interfaces ge-0/0/0 detail | match queue

# Show forwarding classes
show class-of-service forwarding-class

# Show scheduler map
show class-of-service scheduler-map

# Show DSCP classifiers
show class-of-service classifier type dscp
```

---

## 12. Useful JunOS Filters and Pipes

```
# Filter output
show interfaces | match up|down|error
show bgp summary | match Establ|Active|Idle

# Match and display surrounding lines
show log messages | match BGP | last 50

# Count lines
show bgp summary | count Establ

# Show specific section
show configuration protocols bgp
show configuration interfaces ge-0/0/0
show configuration | display set    # show config in set commands format

# Resolve names
show route 8.8.8.8/32 | no-resolve    # show IPs not hostnames
```

---

## 13. Operational Shortcuts

```
# Repeat a command (show interfaces every 2 seconds)
monitor interface ge-0/0/0
monitor interface traffic        # live traffic counter

# Live syslog
monitor start messages           # stream syslog to terminal
monitor stop

# Ping and traceroute with source
ping 10.0.0.1 source 1.1.1.1
ping 10.0.0.1 count 100 rapid
traceroute 10.0.0.1 source 1.1.1.1
traceroute mpls ldp 10.0.0.1/32  # MPLS traceroute

# Test policy
test policy <policy-name> <prefix>
```

---

## 14. Escalation Criteria

Escalate to Juniper JTAC (support.juniper.net) if:
- Routing engine crash or reboot (check: `show log messages | match panic|crash|restart`)
- FPC (line card) offline or continually restarting
- Hardware alarms that don't clear after component check
- JunOS process crash (rpd, chassisd, l2cpd)
- Configuration commit fails with internal errors
- BGP/OSPF/IS-IS not recovering after process restart
