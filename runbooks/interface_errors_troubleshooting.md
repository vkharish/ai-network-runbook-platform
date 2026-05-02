# Interface Errors Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of interface errors, link flaps, and physical layer issues on Cisco IOS-XE, Cisco IOS-XR, and Juniper JunOS devices. Interface problems are a primary cause of routing protocol instability (BGP flaps, OSPF neighbor loss, IS-IS adjacency drops).

---

## 1. Interface State Reference

| Admin State | Line Protocol | Meaning |
|-------------|--------------|---------|
| up | up | Interface is fully operational |
| up | down | Physical layer problem (cable, SFP, peer) |
| administratively down | down | Manually shut down — check if intentional |
| up | up (looped) | Loop detected |

---

## 2. Initial Diagnosis

### Step 1: Check Interface Status

**Cisco IOS-XE / IOS-XR:**
```
show interfaces
show interfaces GigabitEthernet0/0/0
show interfaces GigabitEthernet0/0/0 counters
show interfaces status
```

**Juniper JunOS:**
```
show interfaces
show interfaces ge-0/0/0 detail
show interfaces ge-0/0/0 statistics
```

Key counters to check:
- Input errors, CRC errors, framing errors (physical layer issues)
- Output drops (congestion / buffer overflow)
- Runts (< 64 byte frames — duplex mismatch or noise)
- Giants (oversized frames — MTU mismatch)
- Resets (interface being brought down and up)

### Step 2: Check Error Counters in Detail

**Cisco IOS-XR:**
```
show interfaces GigabitEthernet0/0/0/0 detail
```

Look for:
```
Input errors: 1523       ← physical layer problem
  CRC: 1523              ← bad cable, SFP, or duplex mismatch
  Frame: 0
  Overrun: 0
  Ignored: 0
Output errors: 0
  Underruns: 0
  Output buffer failures: 0
```

### Step 3: Check Interface Flap History

**Cisco IOS-XR:**
```
show interfaces GigabitEthernet0/0/0/0 | include flap
show logging | include GigabitEthernet0/0/0/0
```

**Juniper:**
```
show interfaces ge-0/0/0 detail | match "Last flapped"
show log messages | match ge-0/0/0
```

---

## 3. Common Root Causes and Fixes

### 3.1 Physical Layer Issues (CRC / Input Errors)

**Symptom:** High CRC error count, input errors incrementing, interface may flap.

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include CRC|error|reset
show controllers GigabitEthernet0/0/0    # Cisco — shows optical/electrical signal info
```

**Common causes:**
- Bad or damaged fiber/copper cable
- Dirty or faulty SFP/QSFP transceiver
- Incorrect SFP type (e.g., SR SFP on LR link)
- Duplex mismatch (one side auto, other side hard-set)

**Fix:**
1. Replace cable or clean fiber connectors
2. Reseat or replace SFP transceiver
3. Fix duplex mismatch:
```
interface GigabitEthernet0/0/0
  duplex full
  speed 1000
  no shutdown
```

---

### 3.2 Duplex Mismatch

**Symptom:** Interface is up/up but high error rate. One side shows half-duplex, other shows full-duplex.

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include duplex|speed
```

**Fix:** Set both sides to the same speed and duplex explicitly (avoid auto-negotiation on critical links):
```
interface GigabitEthernet0/0/0
  speed 1000
  duplex full
  no shutdown
```

---

### 3.3 Interface Flapping

**Symptom:** Interface repeatedly going up then down. Routing protocols reconverge each time.

**Diagnosis:**
```
show logging | include up|down|GigabitEthernet
show interfaces GigabitEthernet0/0/0 | include resets|flap
show interfaces GigabitEthernet0/0/0 counters    # check if counters are incrementing
```

**Common causes:**
- Physical layer instability (bad cable, SFP degradation)
- Optical power level too low or too high
- BFD timer too aggressive for link quality
- Auto-negotiation failures on high-speed links

**Fix — check optical power (Cisco IOS-XR):**
```
show controllers GigabitEthernet0/0/0/0 phy
show controllers GigabitEthernet0/0/0/0 | include Receive power|Transmit power
```

Acceptable optical power range: typically -3 dBm to -20 dBm (check SFP spec sheet).

**Fix — dampen flapping interface:**
```
interface GigabitEthernet0/0/0
  carrier-delay msec 500    # wait 500ms before declaring link down
  dampening
```

---

### 3.4 Output Drops / Congestion

**Symptom:** Output drops incrementing, traffic experiencing latency or loss.

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include drops|queue
show policy-map interface GigabitEthernet0/0/0    # if QoS applied
```

**Common causes:**
- Link bandwidth exceeded
- QoS policy misconfigured (wrong queue weights)
- Traffic burst exceeding interface buffer

**Fix — check interface bandwidth utilization:**
```
show interfaces GigabitEthernet0/0/0 | include rate
```

If sustained utilization > 80%, consider:
1. Traffic engineering — route some flows to alternate paths
2. QoS — prioritize critical traffic (BGP keepalives, management)
3. Capacity upgrade

---

### 3.5 MTU Mismatch

**Symptom:** Large packets dropped, but small packets pass. Routing protocols up but application traffic fails (especially TCP sessions that negotiate large MSS).

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include MTU
ping <destination> size 1472 df-bit    # test with large packet
```

**Fix:**
```
interface GigabitEthernet0/0/0
  ip mtu 9000                # for jumbo frames
  ip tcp adjust-mss 1452     # adjust MSS for TCP sessions
```

Ensure MTU is consistent end-to-end on the path.

---

### 3.6 Interface Stuck in Administratively Down

**Symptom:** Interface is shut down. Often misconfiguration or intentional maintenance that was not reversed.

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include admin
show running-config interface GigabitEthernet0/0/0
```

**Fix:**
```
interface GigabitEthernet0/0/0
  no shutdown
```

Verify with peer that link should be active before bringing up.

---

### 3.7 High CPU from Interface Polling

**Symptom:** Router CPU high, interface-related process consuming resources.

**Diagnosis:**
```
show processes cpu sorted    # Cisco
show chassis routing-engine  # Juniper
```

**Fix:**
- Disable debug commands if accidentally left on
- Reduce SNMP polling frequency for interface MIBs
- Check for excessive syslog generation from flapping interface

---

## 4. Cisco IOS-XR Specific Commands

```
show interfaces
show interfaces detail
show interfaces counters
show interfaces counters errors
show controllers GigabitEthernet0/0/0/0
show controllers GigabitEthernet0/0/0/0 phy
clear counters GigabitEthernet0/0/0/0
show logging | include GigabitEthernet
show inventory                          # check installed SFPs
```

---

## 5. Juniper JunOS Specific Commands

```
show interfaces ge-0/0/0 detail
show interfaces ge-0/0/0 statistics
show interfaces ge-0/0/0 extensive
show pfe statistics traffic             # packet forwarding engine stats
show chassis hardware                   # check SFP inventory
clear interfaces statistics ge-0/0/0
show log messages | match ge-0/0/0
request interface reconfigure ge-0/0/0  # re-negotiate interface parameters
```

---

## 6. Preventive Checks

Run these regularly during maintenance windows:

```
# Check all interfaces with errors
show interfaces | include error|CRC|reset|drop

# Check interfaces with high utilization
show interfaces | include rate

# Check for any admin-down interfaces
show interfaces status | include disabled
```

---

## 7. Escalation Criteria

Escalate to hardware team or vendor TAC if:
- CRC errors persist after cable/SFP replacement
- Optical power levels are within spec but errors continue
- Interface is flapping more than once per minute despite dampening
- Hardware error messages in logs (ASIC errors, fabric errors)
- Multiple interfaces on the same linecard are failing simultaneously

---

## 8. Post-Resolution Checklist

- [ ] Interface is in up/up state
- [ ] Error counters are not incrementing (clear and recheck after 5 minutes)
- [ ] No output drops observed
- [ ] Routing protocols have reconverged (BGP, OSPF, IS-IS neighbors back up)
- [ ] Traffic flows confirmed by ping and traceroute
- [ ] Physical layer confirmed clean (optical power within spec)
- [ ] Change documented in ITSM system
- [ ] Monitoring alerts cleared
