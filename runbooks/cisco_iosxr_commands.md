# Cisco IOS-XR Command Reference Runbook

## Overview

This runbook is a quick-reference for Cisco IOS-XR CLI commands used during network incident diagnosis. IOS-XR differs significantly from IOS-XE in syntax, commit model, and process architecture. Use this guide alongside protocol-specific runbooks.

---

## 1. IOS-XR Key Differences from IOS-XE

| Feature | IOS-XE | IOS-XR |
|---------|--------|--------|
| Config model | Running config changes instantly | Staged — must `commit` to activate |
| Rollback | `reload` to restore | `rollback configuration` |
| Processes | Monolithic | Distributed (separate processes per feature) |
| Admin mode | `enable` | `admin` (separate admin plane) |
| Interfaces | `GigabitEthernet0/0` | `GigabitEthernet0/0/0/0` (rack/slot/module/port) |

---

## 2. Configuration Workflow

```
# Enter config mode
configure terminal     (or: configure)

# Make changes
interface GigabitEthernet0/0/0/0
  no shutdown

# Preview changes before committing
show configuration running

# Commit (activate the configuration)
commit

# Commit with a label for rollback
commit label fix-bgp-peer

# Rollback to previous commit
rollback configuration last 1

# Show commit history
show configuration commit list

# Abort without committing
abort
```

---

## 3. BGP Commands (IOS-XR)

```
# Show BGP summary
show bgp summary
show bgp ipv4 unicast summary
show bgp vrf all summary

# Show neighbor detail
show bgp neighbors <peer-ip>
show bgp neighbors <peer-ip> detail
show bgp neighbors <peer-ip> | include State|prefix|hold

# Show received/advertised routes
show bgp neighbors <peer-ip> routes
show bgp neighbors <peer-ip> received-routes
show bgp neighbors <peer-ip> advertised-routes

# Show specific prefix
show bgp ipv4 unicast <prefix>
show bgp ipv4 unicast <prefix> detail

# Clear BGP session
clear bgp <peer-ip>
clear bgp <peer-ip> soft in
clear bgp <peer-ip> soft out
clear bgp all *

# Debug (use with caution)
debug bgp neighbor <peer-ip>
debug bgp update
```

---

## 4. OSPF Commands (IOS-XR)

```
# Show OSPF neighbors
show ospf neighbor
show ospf neighbor detail
show ospf neighbor <interface-name>

# Show OSPF database
show ospf database
show ospf database router
show ospf database summary

# Show OSPF interface
show ospf interface
show ospf interface brief

# Show OSPF routes
show route ospf
show ospf route

# Show OSPF process
show ospf

# Clear OSPF process (use with caution — drops all adjacencies)
clear ospf process

# Debug
debug ospf adj
debug ospf events
```

---

## 5. IS-IS Commands (IOS-XR)

```
# Show IS-IS neighbors
show isis neighbors
show isis neighbors detail

# Show IS-IS database
show isis database
show isis database detail
show isis database verbose

# Show IS-IS interface
show isis interface
show isis interface brief

# Show IS-IS route
show isis route
show isis route <prefix>

# Show IS-IS topology
show isis topology

# Show SPF log (convergence events)
show isis spf-log

# Show LSP generation log
show isis lsp-log

# Clear IS-IS process (use with caution)
clear isis process
clear isis neighbors
```

---

## 6. Interface Commands (IOS-XR)

```
# Show interface status
show interfaces
show interfaces GigabitEthernet0/0/0/0
show interfaces GigabitEthernet0/0/0/0 brief
show interfaces GigabitEthernet0/0/0/0 detail

# Show interface counters
show interfaces GigabitEthernet0/0/0/0 counters
show interfaces GigabitEthernet0/0/0/0 counters rates

# Show physical layer detail
show controllers GigabitEthernet0/0/0/0
show controllers GigabitEthernet0/0/0/0 phy

# Show optical transceiver info
show controllers GigabitEthernet0/0/0/0 | include power|wavelength

# Clear interface counters
clear counters GigabitEthernet0/0/0/0

# Bring interface up/down
interface GigabitEthernet0/0/0/0
  no shutdown     # bring up
  shutdown        # bring down
  commit
```

---

## 7. Routing Table Commands (IOS-XR)

```
# Show routing table
show route
show route ipv4
show route ipv6

# Show specific prefix
show route 10.0.0.0/8
show route 10.0.0.1/32 detail

# Show routing table summary
show route summary

# Show routes by protocol
show route ospf
show route bgp
show route isis
show route static
show route connected
show route local

# Show CEF (Cisco Express Forwarding)
show cef 10.0.0.1/32
show cef 10.0.0.1/32 detail
show cef detail
show cef hardware egress location 0/0/CPU0
```

---

## 8. MPLS / LDP Commands (IOS-XR)

```
# Show LDP sessions
show mpls ldp neighbor
show mpls ldp neighbor detail
show mpls ldp session

# Show LDP bindings
show mpls ldp bindings
show mpls ldp bindings 10.0.0.1/32

# Show MPLS forwarding
show mpls forwarding
show mpls forwarding detail
show mpls forwarding labels <label>

# Show MPLS interfaces
show mpls interfaces

# Clear LDP session
clear mpls ldp neighbor <ip>
```

---

## 9. System Health Commands (IOS-XR)

```
# Show CPU and memory
show processes cpu
show processes memory
show processes cpu sorted

# Show system logs
show logging
show logging | include ERROR|WARN|BGP|OSPF|ISIS
show log last 100

# Show version and hardware
show version
show inventory

# Show installed packages
show install active

# Show platform
show platform
show platform vm

# Show environment (fans, power, temperature)
show environment
show environment temperature
show environment power

# Show redundancy
show redundancy
show redundancy summary
```

---

## 10. Useful Filters and Pipes

```
# Filter output
show interfaces | include up|down|error|rate
show bgp summary | include Established|Active|Idle

# Begin from matching line
show running-config | begin router bgp
show running-config | begin interface GigabitEthernet0/0/0/0

# Section of config
show running-config interface GigabitEthernet0/0/0/0
show running-config router bgp
show running-config router ospf

# Count matching lines
show bgp summary | count Established

# Exclude lines
show interfaces | exclude down
```

---

## 11. Configuration Rollback Procedure

If a configuration change causes issues:

```
# Check recent commits
show configuration commit list

# Rollback last commit
rollback configuration last 1

# Rollback to specific commit
rollback configuration to <commit-id>

# Rollback and commit immediately
rollback configuration last 1
commit
```

---

## 12. Escalation Criteria

Escalate to Cisco TAC (open case via CCO) if:
- IOS-XR process crash (check: `show logging | include crash|reload|aborted`)
- ASIC or linecard hardware errors
- Configuration commit fails repeatedly
- BGP/OSPF/IS-IS process not responding after `clear` command
- Memory leak suspected (memory utilization growing without release)
