# MPLS and LDP Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of MPLS (Multiprotocol Label Switching) forwarding issues and LDP (Label Distribution Protocol) session failures. MPLS is foundational to VPN services, traffic engineering, and QoS in service provider and enterprise core networks.

---

## 1. MPLS and LDP Concepts

| Term | Meaning |
|------|---------|
| LDP | Label Distribution Protocol — distributes labels between MPLS routers |
| LSR | Label Switch Router — forwards packets based on labels |
| LSP | Label Switched Path — end-to-end label forwarding path |
| FEC | Forwarding Equivalence Class — group of packets forwarded the same way |
| LIB | Label Information Base — all labels learned from LDP peers |
| LFIB | Label Forwarding Information Base — active forwarding table |
| PHP | Penultimate Hop Popping — last router before egress pops the label |

---

## 2. Initial Diagnosis

### Step 1: Check LDP Session Status

**Cisco IOS-XE / IOS-XR:**
```
show mpls ldp neighbor
show mpls ldp neighbor detail
show mpls ldp session
```

**Juniper JunOS:**
```
show ldp session
show ldp session detail
show ldp neighbor
```

Session states: Non Existent → Initialized → OpenSent → OpenReceived → Operational

Look for:
- All expected neighbors in Operational state
- Session uptime (resets indicate instability)
- Messages sent/received incrementing

### Step 2: Check MPLS Interfaces

**Cisco IOS-XR:**
```
show mpls interfaces
show mpls ldp interface
```

**Juniper:**
```
show ldp interface
show mpls interface
```

Verify LDP is enabled on all core-facing interfaces.

### Step 3: Check Label Bindings

**Cisco:**
```
show mpls ldp bindings
show mpls ldp bindings 10.0.0.1/32 detail
show mpls forwarding-table
```

**Juniper:**
```
show ldp database
show route table mpls.0
```

---

## 3. Common Root Causes and Fixes

### 3.1 LDP Session Not Establishing

**Symptom:** No LDP neighbor shown. MPLS forwarding not working end-to-end.

**Diagnosis:**
```
show mpls ldp neighbor
show mpls ldp discovery         # check if hellos are being sent
show logging | include LDP
```

LDP uses UDP 646 for discovery (hellos) and TCP 646 for session establishment.

**Common causes:**
- LDP not enabled on interface
- ACL blocking UDP/TCP port 646
- Router-ID mismatch (LDP uses highest loopback IP by default)
- IGP route to peer's loopback not present

**Fix — enable LDP on interface (Cisco IOS-XR):**
```
router ospf 1
  mpls ldp sync                 # ensure IGP and LDP are synchronized
!
mpls ldp
  interface GigabitEthernet0/0/0/0
  !
  router-id 1.1.1.1
```

**Fix — verify reachability:**
```
ping 2.2.2.2 source 1.1.1.1    # ping peer loopback
show ip route 2.2.2.2           # ensure route is in IGP
```

---

### 3.2 LDP Session Flapping

**Symptom:** LDP neighbor repeatedly dropping and re-establishing. MPLS traffic blackholed during drops.

**Diagnosis:**
```
show mpls ldp neighbor | include Up time|Sessions
show logging | include LDP
```

**Common causes:**
- Underlying IGP route to peer loopback flapping (check OSPF/IS-IS)
- LDP hello hold timer mismatch
- MD5 authentication mismatch
- TCP session being reset (MTU issues on TCP 646)

**Fix — match hello timers:**
```
mpls ldp
  holdtime 45             # default is 15 seconds
  discovery hello holdtime 15
  discovery hello interval 5
```

**Fix — MD5 authentication:**
```
mpls ldp
  neighbor 2.2.2.2 password <shared-key>
```

---

### 3.3 Missing Label Bindings

**Symptom:** LDP session is Operational but some prefixes have no label binding.

**Diagnosis:**
```
show mpls ldp bindings | include No label
show mpls ldp bindings 10.1.1.0/24
```

**Common causes:**
- Prefix not in IGP (LDP only distributes labels for IGP prefixes by default)
- LDP ACL filtering label advertisements
- Label space exhausted (rare)

**Fix — check LDP ACL:**
```
show mpls ldp bindings filter    # check if ACL applied
show running-config | section mpls ldp
```

**Fix — if prefix not in IGP, redistribute:**
```
router ospf 1
  redistribute connected subnets route-map CONNECTED_TO_OSPF
```

---

### 3.4 MPLS Forwarding Failure (Black Hole)

**Symptom:** Traffic entering MPLS network is dropped. Traceroute shows asterisks on MPLS hops.

**Diagnosis:**
```
show mpls forwarding-table
show mpls forwarding-table 10.0.0.1/32 detail
traceroute mpls ipv4 10.0.0.1/32 source 1.1.1.1
```

**Check the LFIB entry:**
```
show mpls forwarding-table | include <destination>
```

Expected output:
```
Local  Outgoing    Prefix         Bytes tag  Outgoing  Next Hop
tag    tag or VC   or Tunnel Id   Switched   Interface
100    200         10.0.0.1/32    1234       Gi0/0/0   10.1.1.2
```

If "No label" or "Pop label" in unexpected place — LDP convergence issue.

**Fix — clear and re-establish LDP session:**
```
clear mpls ldp neighbor 2.2.2.2    # hard reset of LDP session
```

---

### 3.5 PHP (Penultimate Hop Popping) Misconfiguration

**Symptom:** Egress router receiving labeled packets when it expects unlabeled.

**Diagnosis:**
```
show mpls ldp bindings | include implicit-null    # PHP enabled
show mpls ldp bindings | include explicit-null    # PHP disabled (sends explicit null)
```

**Fix — enable explicit null to preserve QoS markings:**
```
mpls ldp explicit-null
```

---

### 3.6 MPLS MTU Issues

**Symptom:** Large packets dropped in MPLS network. ICMP unreachables for "fragmentation needed".

**Diagnosis:**
```
show interfaces GigabitEthernet0/0/0 | include MTU
ping 10.0.0.1 size 1500 df-bit    # should fail if MPLS MTU not increased
ping 10.0.0.1 size 1476 df-bit    # should succeed (1500 - 2x4 byte labels)
```

Each MPLS label adds 4 bytes. For 2 label stack: IP MTU must be 1500 - 8 = 1492.

**Fix:**
```
interface GigabitEthernet0/0/0
  mpls mtu 1508              # increase MPLS MTU to accommodate label stack
```

---

## 4. MPLS Traffic Engineering (TE) Troubleshooting

### Check RSVP tunnels
```
show mpls traffic-eng tunnels
show mpls traffic-eng tunnels brief
show mpls traffic-eng tunnels state down
```

### Check RSVP neighbors
```
show ip rsvp neighbor
show ip rsvp session
```

### Force tunnel re-signaling
```
mpls traffic-eng reoptimize    # reoptimize all TE tunnels
clear ip rsvp hello instance submode    # clear RSVP hello state
```

---

## 5. Cisco IOS-XR Specific Commands

```
show mpls ldp neighbor
show mpls ldp neighbor detail
show mpls ldp bindings
show mpls ldp interface
show mpls ldp discovery
show mpls forwarding
show mpls forwarding detail
show mpls forwarding labels <label>
clear mpls ldp neighbor <ip>
```

---

## 6. Juniper JunOS Specific Commands

```
show ldp session
show ldp session detail
show ldp neighbor
show ldp database
show ldp interface
show route table mpls.0
show mpls lsp
show mpls lsp extensive
clear ldp session
clear ldp statistics
```

---

## 7. Escalation Criteria

Escalate to MPLS/core network team or vendor TAC if:
- LDP sessions flap more than 5 times per hour after fixes
- MPLS forwarding table is missing large number of expected labels
- RSVP signaling failures that cannot be resolved by clearing sessions
- MPLS hardware forwarding errors (check ASIC/linecard logs)
- VPN (L2VPN/L3VPN) services are impacted for multiple customers

---

## 8. Post-Resolution Checklist

- [ ] All LDP sessions are in Operational state
- [ ] Label bindings present for all IGP prefixes
- [ ] MPLS forwarding table has entries with valid outgoing labels
- [ ] End-to-end traceroute shows MPLS labels on core hops
- [ ] PHP behavior is correct (implicit-null or explicit-null as designed)
- [ ] VPN services restored and traffic flowing
- [ ] Change documented in ITSM system
- [ ] Monitoring alerts cleared
