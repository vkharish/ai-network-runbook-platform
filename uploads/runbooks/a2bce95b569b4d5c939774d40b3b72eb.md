# BGP Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of BGP (Border Gateway Protocol) session failures
in a multi-vendor environment (Cisco IOS-XE and Juniper JunOS). Use this guide when a BGP
peer is stuck in Idle, Active, or Connect state, or when prefixes are missing from the routing table.

---

## 1. BGP Session States

| State | Meaning |
|-------|---------|
| Idle | BGP is not attempting to connect. Usually blocked by policy or interface down. |
| Connect | TCP connection being attempted. Peer may be unreachable. |
| Active | TCP SYN sent, waiting for response. Peer is not responding. |
| OpenSent | TCP connection established, BGP OPEN message sent. |
| OpenConfirm | OPEN received, waiting for KEEPALIVE. |
| Established | Session is up and exchanging prefixes. |

A session stuck in **Active** or **Connect** state indicates a Layer 3 reachability or
TCP port 179 connectivity problem.

---

## 2. Initial Diagnosis

### Step 1: Check BGP Summary

**Cisco IOS-XE:**
```
show bgp summary
show bgp ipv4 unicast summary
```

**Juniper JunOS:**
```
show bgp summary
show bgp neighbor
```

Look for:
- Peer state (should be Established)
- Uptime (resets indicate flapping)
- Prefixes received (0 may indicate filtering issue)

### Step 2: Verify Interface and IP Reachability

```
ping <peer-ip> source <local-interface-ip>
traceroute <peer-ip>
show interface <interface-name>
```

Check:
- Interface is up/up (not administratively down)
- IP address is correctly configured
- No duplex or MTU mismatch

### Step 3: Check TCP Port 179

```
telnet <peer-ip> 179
```

If telnet fails, a firewall or ACL is blocking BGP traffic.

---

## 3. Common Root Causes and Fixes

### 3.1 Incorrect Neighbor IP or AS Number

**Symptom:** Session stays in Idle or Active.

**Diagnosis:**
```
show running-config | section bgp
show bgp neighbors <peer-ip>
```

**Fix:**
```
router bgp <local-as>
  no neighbor <wrong-ip> remote-as <as>
  neighbor <correct-ip> remote-as <correct-as>
```

---

### 3.2 Authentication Mismatch (MD5 Password)

**Symptom:** TCP connection established but session drops immediately. Logs show
"MD5 digest mismatch" or "Bad Message Length".

**Diagnosis (Cisco):**
```
show bgp neighbors <peer-ip> | include password
debug ip bgp <peer-ip> events
```

**Fix:** Ensure both peers have the same MD5 key:
```
neighbor <peer-ip> password <shared-key>
```

---

### 3.3 TTL / EBGP Multihop Issue

**Symptom:** EBGP peer across multiple hops fails to establish.

**Fix:**
```
neighbor <peer-ip> ebgp-multihop <hop-count>
neighbor <peer-ip> update-source <loopback>
```

---

### 3.4 Route Policy Filtering All Prefixes

**Symptom:** Session is Established but 0 prefixes received.

**Diagnosis:**
```
show bgp neighbors <peer-ip> | include policy
show route-map <policy-name>
show ip bgp neighbors <peer-ip> received-routes
```

**Fix:** Review inbound route-map and ensure prefixes are permitted:
```
route-map ALLOW_ALL permit 10
  match ip address prefix-list ALL_PREFIXES
```

---

### 3.5 BGP Flapping (Repeated Session Resets)

**Symptom:** Uptime in BGP summary resets frequently.

**Diagnosis:**
```
show bgp neighbors <peer-ip> | include reset
show log | include BGP
```

Common causes:
- Hold timer expiry (keepalive not reaching peer in time)
- Interface flapping
- Route reflector loop

**Fix for hold timer:**
```
neighbor <peer-ip> timers 10 30
```

---

## 4. Cisco IOS-XE Specific Commands

```
show bgp ipv4 unicast neighbors <peer-ip>
show bgp ipv4 unicast rib-failure
show ip route bgp
debug ip bgp <peer-ip> updates
clear ip bgp <peer-ip> soft
```

Use `soft` reset to avoid dropping the session when troubleshooting prefix issues.

---

## 5. Juniper JunOS Specific Commands

```
show bgp neighbor <peer-ip>
show route protocol bgp
show route receive-protocol bgp <peer-ip>
show route advertising-protocol bgp <peer-ip>
clear bgp neighbor <peer-ip>
```

Check for policy issues:
```
show policy <policy-name>
test policy <policy-name> <prefix>
```

---

## 6. Escalation Criteria

Escalate to senior network engineer or vendor TAC if:
- Session flaps more than 5 times in 10 minutes despite fixes
- Route reflector or BGP confederation is involved
- BGP process is consuming high CPU (> 80% sustained)
- Prefix count drops unexpectedly across multiple peers simultaneously

---

## 7. Post-Resolution Checklist

- [ ] BGP session in Established state
- [ ] Expected prefix count matches baseline
- [ ] No recent resets in `show bgp summary`
- [ ] Change documented in ITSM system
- [ ] Root cause confirmed and permanent fix applied
- [ ] Monitoring alert cleared
