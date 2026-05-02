# QoS Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of Quality of Service (QoS) issues including traffic drops in priority queues, DSCP marking problems, policing/shaping misconfigurations, and congestion management failures in Cisco IOS-XE, IOS-XR, and Juniper JunOS environments.

---

## 1. QoS Model Reference

### DSCP Values (Most Common)
| DSCP Name | Value | Use Case |
|-----------|-------|----------|
| EF | 46 (101110) | Voice, real-time (strict priority) |
| AF41 | 34 | Video conferencing |
| AF31 | 26 | Call signaling |
| AF21 | 18 | Transactional data |
| AF11 | 10 | Bulk data |
| CS3 | 24 | Network signaling (BGP, OSPF) |
| BE/CS0 | 0 | Best effort (default) |

### Queue Types
- **PQ (Priority Queue):** Strict priority — always serviced first. Risk of starvation for lower queues.
- **CBWFQ (Class-Based Weighted Fair Queue):** Bandwidth guarantee per class.
- **LLQ (Low Latency Queue):** Priority queue + CBWFQ — best for voice/video.
- **WRED (Weighted Random Early Detection):** Proactive drop before queue fills.

---

## 2. Initial Diagnosis

### Step 1: Check Policy-Map Applied to Interface

**Cisco IOS-XE / IOS-XR:**
```
show policy-map interface GigabitEthernet0/0/0
show policy-map interface GigabitEthernet0/0/0 output
```

**Juniper JunOS:**
```
show class-of-service interface ge-0/0/0
show firewall filter <filter-name> counter
```

Look for:
- Packets/bytes matched per class
- Drops per class (should be near zero for critical traffic)
- Queue depth and tail drops

### Step 2: Check Class Map Matching

**Cisco:**
```
show class-map
show policy-map
show policy-map interface GigabitEthernet0/0/0 class VOICE
```

### Step 3: Check DSCP Markings on Incoming Traffic

```
show policy-map interface GigabitEthernet0/0/0 input
```

If traffic is not being classified correctly, markings may be wrong at ingress.

---

## 3. Common Root Causes and Fixes

### 3.1 Voice Traffic Drops in Priority Queue

**Symptom:** VoIP calls experiencing jitter, delay, or drops. Priority queue shows drops.

**Diagnosis:**
```
show policy-map interface GigabitEthernet0/0/0 | include VOICE|drops|police
```

**Common causes:**
- Priority queue bandwidth limit too low (police rate exceeded)
- Voice traffic not marked EF (DSCP 46) — falls into wrong queue
- Link congestion — priority queue bandwidth exceeds available bandwidth

**Fix — verify EF marking:**
```
show policy-map interface GigabitEthernet0/0/0 class VOICE
```

If packets not matching VOICE class — check upstream DSCP marking:
```
show policy-map interface GigabitEthernet0/0/0 input class MARK_VOICE
```

**Fix — increase priority bandwidth:**
```
policy-map WAN_QOS
  class VOICE
    priority 2000      # 2 Mbps strict priority
    police rate 2000000 bps
      conform-action transmit
      exceed-action drop
```

---

### 3.2 Traffic Not Matching Expected Class

**Symptom:** Traffic going to default/best-effort class instead of expected class.

**Diagnosis:**
```
show class-map VOICE
show policy-map interface GigabitEthernet0/0/0 class VOICE    # check if counter incrementing
show policy-map interface GigabitEthernet0/0/0 class class-default    # if high — traffic misclassified
```

**Fix — verify ACL or DSCP match in class-map:**
```
show class-map VOICE
# Example:
# class-map match-any VOICE
#   match dscp ef
#   match dscp cs5

show ip access-list VOICE_ACL    # if matching by ACL
```

If DSCP is being re-marked by intermediate device to 0 (BE), apply remarking at ingress:
```
policy-map MARK_INBOUND
  class VOIP_PORTS
    set dscp ef
```

---

### 3.3 Policing Drops on Critical Traffic

**Symptom:** Application traffic is being dropped even though link is not congested.

**Diagnosis:**
```
show policy-map interface GigabitEthernet0/0/0 | include police|conform|exceed|violate
```

**Fix — check police rate:**
```
policy-map WAN_QOS
  class BUSINESS_DATA
    police rate 10000000 bps burst 500000
      conform-action transmit
      exceed-action set-dscp-transmit AF21    # downgrade instead of drop
      violate-action drop
```

Consider using `shape` instead of `police` on egress to buffer bursts rather than drop:
```
policy-map WAN_QOS
  class BUSINESS_DATA
    shape average 10000000    # shape to 10 Mbps — buffers bursts
```

---

### 3.4 WRED Not Activating

**Symptom:** Queue filling to 100% and tail-dropping instead of WRED proactively dropping.

**Diagnosis:**
```
show policy-map interface GigabitEthernet0/0/0 class BULK_DATA
```

Look for "random-detect" in policy. If not shown, WRED is not configured.

**Fix — enable WRED with DSCP-based thresholds:**
```
policy-map WAN_QOS
  class BULK_DATA
    bandwidth percent 30
    random-detect dscp-based
    random-detect dscp AF11 20 40 10    # min-thresh max-thresh mark-prob
    random-detect dscp AF12 25 45 10
```

---

### 3.5 Egress Shaping Too Aggressive

**Symptom:** All traffic slow even when link has capacity.

**Diagnosis:**
```
show policy-map interface GigabitEthernet0/0/0 | include shape|rate
show interfaces GigabitEthernet0/0/0 | include rate
```

If shaped rate is much lower than interface rate and traffic is being delayed:

**Fix — match shaping rate to actual committed bandwidth:**
```
policy-map PARENT_SHAPER
  class class-default
    shape average 100000000    # shape to 100 Mbps if circuit is 100 Mbps
    service-policy WAN_QOS     # child policy for classification
```

---

### 3.6 QoS Not Applied After Routing Change

**Symptom:** QoS was working, then a failover or route change occurred and policy seems missing.

**Diagnosis:**
```
show policy-map interface GigabitEthernet0/0/0    # check if policy applied
show running-config interface GigabitEthernet0/0/0 | include service-policy
```

After a failover, traffic may be exiting a different interface where QoS policy is not applied.

**Fix — apply policy to all egress interfaces:**
```
interface GigabitEthernet0/0/1
  service-policy output WAN_QOS
```

---

## 4. Cisco IOS-XR Specific Commands

```
show policy-map interface
show policy-map interface GigabitEthernet0/0/0/0 input
show policy-map interface GigabitEthernet0/0/0/0 output
show qos interface GigabitEthernet0/0/0/0 output
show qos interface GigabitEthernet0/0/0/0 output detail
show controllers GigabitEthernet0/0/0/0 stats    # hardware queue stats
```

---

## 5. Juniper JunOS Specific Commands

```
show class-of-service interface ge-0/0/0
show class-of-service interface ge-0/0/0 detail
show interfaces ge-0/0/0 detail | match queue
show firewall filter <filter-name>
show firewall filter <filter-name> counter
show class-of-service forwarding-class
show class-of-service scheduler-map
```

---

## 6. Escalation Criteria

Escalate to senior network engineer or vendor TAC if:
- Voice quality issues persist after QoS policy verification and correction
- Hardware queue drops occurring even when link is not congested (possible ASIC bug)
- QoS policy applied correctly but DSCP markings being stripped by intermediate device (check SLA with provider)
- MQC (Modular QoS CLI) configuration is too complex to troubleshoot without platform specialist

---

## 7. Post-Resolution Checklist

- [ ] Traffic classified correctly into expected classes (verified by counters)
- [ ] No drops in priority/critical traffic classes
- [ ] Voice MOS score acceptable (> 3.5)
- [ ] DSCP markings preserved end-to-end
- [ ] Policy applied on all relevant interfaces (primary and backup)
- [ ] WRED active on bulk data classes (preventing tail drop)
- [ ] Change documented in ITSM system
- [ ] Monitoring alerts cleared
