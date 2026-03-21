# OSPF Troubleshooting Runbook

## Overview

This runbook covers diagnosis and resolution of OSPF (Open Shortest Path First) neighbor
adjacency failures and routing issues in a multi-vendor environment. Use this guide when
OSPF neighbors are stuck in DOWN, INIT, or 2-WAY state, or when expected routes are
missing from the OSPF database.

---

## 1. OSPF Neighbor States

| State | Meaning |
|-------|---------|
| Down | No hellos received from neighbor. |
| Init | Hello received but local router ID not in neighbor's hello. |
| 2-Way | Bidirectional communication established. DR/BDR election may occur. |
| ExStart | Master/slave negotiation for database exchange. |
| Exchange | Database Description packets being exchanged. |
| Loading | LSA requests being sent. |
| Full | Adjacency complete. Routes exchanged. |

Neighbors on point-to-point links should reach **Full**. On broadcast segments,
non-DR/BDR routers reach **2-Way** with each other but **Full** with DR and BDR.

---

## 2. Initial Diagnosis

### Step 1: Check OSPF Neighbor Table

**Cisco IOS-XE:**
```
show ip ospf neighbor
show ip ospf neighbor detail
```

**Juniper JunOS:**
```
show ospf neighbor
show ospf neighbor detail
```

Look for neighbors stuck in Init or 2-Way when Full is expected.

### Step 2: Verify Hello Parameters Match

OSPF neighbors will not form adjacency if these parameters differ:
- Hello interval (default 10s on broadcast, 30s on NBMA)
- Dead interval (default 4x hello interval)
- Area ID
- Authentication type and key
- MTU (when IP MTU check is enabled)
- Stub area flag

```
show ip ospf interface <interface>
show ip ospf neighbor <neighbor-id> detail
```

---

## 3. Common Root Causes and Fixes

### 3.1 Hello/Dead Timer Mismatch

**Symptom:** Neighbor stuck in Init or Down. Hellos received but adjacency drops.

**Diagnosis:**
```
show ip ospf interface <interface> | include Hello|Dead
debug ip ospf hello
```

**Fix:** Match timers on both sides:
```
interface <interface>
  ip ospf hello-interval 10
  ip ospf dead-interval 40
```

---

### 3.2 Area ID Mismatch

**Symptom:** No neighbor relationship at all. Debug shows mismatched area.

**Diagnosis:**
```
show ip ospf interface brief
debug ip ospf adj
```

**Fix:** Ensure both sides use the same area:
```
interface <interface>
  ip ospf <process-id> area <correct-area>
```

---

### 3.3 MTU Mismatch

**Symptom:** Neighbors stuck in ExStart/Exchange state, never reaching Full.

**Diagnosis:**
```
show ip ospf neighbor detail | include Dead|State|MTU
show interface <interface> | include MTU
```

**Fix Option A** — Match MTU on both interfaces:
```
interface <interface>
  ip mtu 1500
```

**Fix Option B** — Disable MTU check (not recommended in production):
```
interface <interface>
  ip ospf mtu-ignore
```

---

### 3.4 Authentication Mismatch

**Symptom:** Neighbor drops after Init. Logs show authentication failure.

**Diagnosis:**
```
debug ip ospf adj
show ip ospf interface <interface> | include auth
```

**Fix:** Ensure same authentication type and key:
```
interface <interface>
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 <shared-key>
```

---

### 3.5 Duplicate Router ID

**Symptom:** Flapping neighbors, unexpected route changes.

**Diagnosis:**
```
show ip ospf | include Router ID
show ip ospf database | include Router
```

**Fix:** Assign unique router IDs:
```
router ospf <process-id>
  router-id <unique-ip>
```

---

### 3.6 Network Type Mismatch

**Symptom:** Neighbors stuck in 2-Way on a point-to-point link.

**Diagnosis:**
```
show ip ospf interface <interface> | include Network Type
```

**Fix:** Match network type on both ends:
```
interface <interface>
  ip ospf network point-to-point
```

---

## 4. OSPF Database Verification

After adjacency is Full, verify the LSDB is complete:

```
show ip ospf database
show ip ospf database router
show ip ospf database summary
show ip ospf database external
```

Missing LSAs indicate a filtering issue or area boundary problem.

Check route installation:
```
show ip route ospf
show ip ospf rib
```

---

## 5. Juniper JunOS Specific Commands

```
show ospf interface detail
show ospf database
show ospf route
show ospf statistics
clear ospf neighbor <neighbor-ip>
```

Policy checking:
```
show policy <ospf-export-policy>
test policy <policy-name> <prefix>
```

---

## 6. Escalation Criteria

Escalate if:
- Adjacency flaps repeatedly (more than 3 times in 5 minutes)
- OSPF process is consuming > 70% CPU
- Full LSDB flooding occurring across large topology
- SPF calculations happening more than once per minute
- Route oscillation visible in the RIB

---

## 7. Post-Resolution Checklist

- [ ] All expected OSPF neighbors in Full state
- [ ] OSPF database matches across all routers in area
- [ ] Routes present in RIB (`show ip route ospf`)
- [ ] No recent neighbor state changes in logs
- [ ] Change documented in ITSM system
- [ ] Monitoring alert cleared
