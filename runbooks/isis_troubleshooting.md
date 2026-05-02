# IS-IS Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of IS-IS (Intermediate System to Intermediate System) adjacency failures, route leaking issues, and convergence problems in multi-vendor environments (Cisco IOS-XE, Cisco IOS-XR, and Juniper JunOS).

---

## 1. IS-IS Adjacency States

| State | Meaning |
|-------|---------|
| Down | No hello packets received from neighbor |
| Initializing | Hello received but not yet bidirectional |
| Up | Full adjacency established, routes exchanged |

IS-IS uses two levels:
- **Level 1 (L1):** Intra-area routing (same area)
- **Level 2 (L2):** Inter-area / backbone routing
- **L1/L2:** Router participates in both levels

---

## 2. Initial Diagnosis

### Step 1: Check IS-IS Adjacency Status

**Cisco IOS-XE / IOS-XR:**
```
show isis neighbors
show isis neighbors detail
show isis adjacency
```

**Juniper JunOS:**
```
show isis adjacency
show isis adjacency detail
```

Look for:
- Adjacency state (should be Up)
- Circuit type (L1, L2, or L1L2)
- Hold time remaining (if low, hello packets are delayed)
- SNPA (MAC address of neighbor)

### Step 2: Check IS-IS Interface Configuration

**Cisco IOS-XR:**
```
show isis interface
show isis interface GigabitEthernet0/0/0/0 detail
```

**Juniper JunOS:**
```
show isis interface
show isis interface detail
```

Verify:
- Interface is enabled for IS-IS
- Correct level (L1/L2) configured
- Metric is set correctly
- Passive mode not accidentally enabled

### Step 3: Check IS-IS Database

**Cisco:**
```
show isis database
show isis database detail
show isis database verbose
```

**Juniper:**
```
show isis database
show isis database detail
```

Look for:
- LSP sequence numbers incrementing (indicates topology changes)
- Overload bit set on any router
- Expired LSPs (sequence number 0xFFFF)

---

## 3. Common Root Causes and Fixes

### 3.1 MTU Mismatch

**Symptom:** Adjacency stays in Initializing state, never reaches Up.

**Diagnosis:**
```
show interface GigabitEthernet0/0/0 | include MTU
show isis interface detail | include MTU
```

IS-IS sends full LSPs in hello packets. If MTU differs between peers, large packets are dropped and adjacency cannot form.

**Fix:**
```
interface GigabitEthernet0/0/0
  ip mtu 1500
  isis mtu 1497
```

Ensure MTU matches on both ends. IS-IS PDU size = interface MTU - 3 bytes.

---

### 3.2 Authentication Mismatch

**Symptom:** Adjacency flaps or stays Down. Logs show authentication failures.

**Diagnosis (Cisco IOS-XR):**
```
show isis neighbors
show logging | include ISIS
debug isis adj-packets
```

**Fix — HMAC-MD5 authentication:**
```
router isis 1
  interface GigabitEthernet0/0/0/0
    hello-password hmac-md5 <password>
  !
  lsp-password hmac-md5 <password>
```

Ensure the same password is configured on both sides at both hello and LSP levels.

---

### 3.3 Area ID Mismatch

**Symptom:** L1 adjacency cannot form. L2 may still form.

**Diagnosis:**
```
show isis neighbors detail | include Area
show running-config | include net
```

IS-IS uses a NET (Network Entity Title) address: `49.0001.0000.0000.0001.00`
- `49` = AFI (private use)
- `0001` = Area ID
- `0000.0000.0001` = System ID (unique per router)
- `00` = NSEL (always 00 for routers)

**Fix:** Ensure L1 neighbors are in the same area:
```
router isis 1
  net 49.0001.0000.0000.0002.00
```

L2 neighbors do not need matching area IDs.

---

### 3.4 Duplicate System ID

**Symptom:** Adjacency flaps, error logs show "Duplicate system ID detected".

**Diagnosis:**
```
show isis database | include System-ID
show logging | include duplicate
```

**Fix:** Assign a unique System ID to each router. System ID is typically derived from the router's loopback IP:
```
# Loopback 1.2.3.4 → System ID 0100.2003.0004
router isis 1
  net 49.0001.0100.2003.0004.00
```

---

### 3.5 Overload Bit Set

**Symptom:** Routes from this router are not used by neighbors even though adjacency is Up.

**Diagnosis:**
```
show isis database detail | include Overload
show isis neighbors detail
```

The overload bit signals to other routers: "do not use me for transit." It is set:
- Manually for maintenance
- Automatically when the router is booting (on-startup timer)
- When IS-IS cannot store full topology (memory exhaustion)

**Fix — clear manually set overload:**
```
# Cisco IOS-XR
router isis 1
  no set-overload-bit
```

**Fix — allow boot convergence before clearing overload:**
```
router isis 1
  set-overload-bit on-startup wait-for-bgp
```

---

### 3.6 IS-IS Not Running on Interface

**Symptom:** Expected neighbor not appearing. Interface is up/up.

**Diagnosis:**
```
show isis interface brief
show running-config interface GigabitEthernet0/0/0
```

**Fix (Cisco IOS-XR):**
```
router isis 1
  interface GigabitEthernet0/0/0/0
    address-family ipv4 unicast
      metric 10
    !
    circuit-type level-2-only
```

**Fix (Juniper):**
```
set protocols isis interface ge-0/0/0.0 level 2
```

---

### 3.7 IS-IS Route Not in Routing Table

**Symptom:** Adjacency is Up but routes from IS-IS are missing.

**Diagnosis:**
```
show isis route
show ip route isis
show route protocol isis    # Juniper
```

Check for:
- Redistribution filters blocking routes
- Metric set too high (unreachable)
- Route leaking between L1 and L2 not configured

**Fix — enable L1 to L2 route leaking:**
```
router isis 1
  address-family ipv4 unicast
    propagate-level 1 into level 2
```

---

## 4. Cisco IOS-XR Specific Commands

```
show isis neighbors
show isis interface
show isis database
show isis database detail
show isis route
show isis topology
show isis spf-log
show isis lsp-log
clear isis process
clear isis neighbors
debug isis adj-packets
debug isis update-packets
```

---

## 5. Juniper JunOS Specific Commands

```
show isis adjacency
show isis adjacency detail
show isis interface
show isis database
show isis database detail
show isis route
show isis statistics
show isis spf
clear isis adjacency all
clear isis database
```

---

## 6. IS-IS Convergence Troubleshooting

### Check SPF calculation logs
```
# Cisco IOS-XR
show isis spf-log

# Juniper
show isis spf brief
```

### Tune timers for faster convergence
```
# Cisco IOS-XR
router isis 1
  address-family ipv4 unicast
    spf-interval maximum-wait 5000 initial-wait 50 secondary-wait 200
  !
  lsp-gen-interval maximum-wait 5000 initial-wait 50 secondary-wait 200
```

---

## 7. Escalation Criteria

Escalate to senior engineer or vendor TAC if:
- IS-IS process is consuming high CPU (> 80% sustained)
- LSP database is corrupted (sequence number wraps)
- IS-IS adjacency flaps more than 10 times per hour after fixes applied
- Overload bit cannot be cleared and traffic is black-holed
- Topology is not converging within expected time after a link failure

---

## 8. Post-Resolution Checklist

- [ ] All expected IS-IS adjacencies are in Up state
- [ ] IS-IS database is synchronized across all routers
- [ ] No overload bit set on production routers
- [ ] Routes are present in routing table with correct metrics
- [ ] SPF log shows no unusual calculation storms
- [ ] Change documented in ITSM system
- [ ] Monitoring alerts cleared
