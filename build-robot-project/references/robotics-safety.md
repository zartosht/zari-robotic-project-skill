# Robotics Safety and Privacy

## Contents

- [Mandatory Approval Gates](#mandatory-approval-gates)
- [Deterministic Actuator Boundary](#deterministic-actuator-boundary)
- [Electrical and Power Safety](#electrical-and-power-safety)
- [Batteries and Stored Energy](#batteries-and-stored-energy)
- [Mechanical and Wearable Safety](#mechanical-and-wearable-safety)
- [Camera, Microphone, Network, and AI Privacy](#camera-microphone-network-and-ai-privacy)
- [Safety Review Before Escalation](#safety-review-before-escalation)

## Mandatory Approval Gates

Require explicit user confirmation before:

- buying or ordering hardware;
- applying power to a new or changed circuit;
- connecting a battery;
- connecting a motor or servo to power;
- introducing, storing, pressurizing, preloading, or releasing hazardous energy, including pressure, gravity, springs, flywheels, heat, or non-electrical actuation;
- uploading firmware capable of causing movement;
- performing the first physical movement test;
- increasing actuator speed, force, torque, travel, or movement range;
- enabling autonomous movement or floor movement;
- enabling an always-listening microphone or a camera;
- transmitting audio, video, location, credentials, or other sensitive data;
- using dangerous tools, mains voltage, or high-current systems;
- building, modifying, or charging custom battery packs;
- proceeding with unresolved voltage, current, polarity, pinout, driver, or compatibility questions.

Approval for one gate does not approve later escalation. Record the exact configuration approved.

## Deterministic Actuator Boundary

Never connect generative or probabilistic AI output directly to an actuator.

Require this control chain:

```text
user or autonomy request
  -> proposed intent
  -> deterministic validator
  -> bounded command
  -> firmware safety checks
  -> driver and actuator
```

Where applicable, commands must include bounded target, speed, force, duration, sequence, and time-to-live. Reject malformed, out-of-range, unauthorized, or stale commands.

Firmware must independently enforce:

- hard motion and timing bounds;
- watchdog stop on communication loss;
- fault-state stop;
- emergency stopping;
- safe startup and restart behavior;
- no movement from malformed or stale input.

For motion capable of injury or material property damage, require a reachable, latching physical stop or non-network power/enable cut-off independent of the app and primary control process. Define whether the safe response is coast, brake, controlled hold, or de-energize; cutting power can itself be hazardous for gravity-loaded systems. Require manual reset, deliberate re-arming, and no automatic movement restart.

For hazardous actuators, also require an independent hardware watchdog or safety supervisor, fail-safe driver-enable behavior, and control-loop deadline monitoring. A watchdog implemented only in the same frozen controller is not an independent safety boundary. Test controller hangs, stalled tasks, stale sensors, communication loss, brownouts, and reboot without automatic resume.

## Electrical and Power Safety

- Do not power motors or servos from controller signal pins.
- Verify source voltage, continuous and peak current, polarity, connector pinout, regulator/driver limits, and stall-current behavior.
- Verify whether logic and power grounds must share a reference.
- Use the correct motor or actuator driver and required protection components.
- Verify the complete current path: wire gauge, PCB traces, breadboard/contact/terminal/connector/switch ratings, fuse or current-limit placement, return-path capacity, and backfeed interaction among USB, charger, battery, and external supplies.
- Do not assume solderless breadboards, header pins, or jumper wires can carry actuator current.
- Start with no load, low speed, small travel, short duration, and mechanical clearance.
- Disconnect all power before changing wiring.
- Stop immediately for heat, odor, smoke, sparking, swelling, repeated resets, violent chatter, damaged insulation, or unexpected motion.

Do not use mains voltage when a certified low-voltage supply can serve the learning goal. Do not improvise high-current wiring or protection.

## Batteries and Stored Energy

Treat batteries as stored-energy systems, not ordinary wires.

- Prefer certified, protected, ready-made packs and matching chargers.
- Verify chemistry, cell count, voltage range, discharge rating, connector, polarity, protection, and charger compatibility.
- Verify exact pack identity, condition, provenance, minimum/nominal/maximum voltage, continuous/peak discharge, BMS/protection, fuse, enclosure/venting, storage, damaged-pack response, and disposal.
- Do not recommend custom lithium packs as a beginner default.
- Never charge unattended, inside a sealed enclosure, or near flammable material.
- Stop for damage, heat, swelling, odor, leakage, or uncertain provenance.

Require specialist supervision for custom packs, mains work, high-current systems, dangerous tools, flying robots, underwater pressure systems, or other hazards beyond the user's demonstrated competence.

## Mechanical and Wearable Safety

- Identify pinch, crush, cut, entanglement, ejection, tip-over, and stored-spring risks.
- Keep people, pets, hair, clothing, and loose objects outside the movement envelope.
- Use guarding, stable fixtures, soft limits, low energy, and a clear test area.
- Test one actuator unloaded before combining actuators or attaching mechanisms.
- Do not increase force or range until earlier acceptance evidence passes.

For wearables, haptics, or body-contact robots:

- limit skin pressure, temperature, vibration intensity, duty cycle, and wear duration;
- prevent circulation restriction, entanglement, and snagging;
- provide a quick-release or breakaway appropriate to the hazard;
- test conservative cues on a non-body mock before body contact;
- do not make navigation or other safety-critical decisions depend solely on unqualified haptic output;
- seek qualified human-factors or clinical review for assistive or medical use.

If the builder or operator may be a minor, require responsible-adult supervision and approval before batteries, tools, power, actuators, or movement.

## Camera, Microphone, Network, and AI Privacy

Default sensitive features to disabled. Require a per-data-type flow covering collection, purpose, destination/provider, transport and storage encryption, access control, retention, deletion, diagnostic-log redaction, third-party processing or training, bystander consent, and offline behavior.

Require:

- local-first processing where practical;
- visible, hardware-tied camera and microphone activity indicators or physical shutter/mute controls where feasible;
- no raw audio or video retention by default;
- separate, user-configurable retention per data type;
- explicit enablement for cloud processing or sensitive-data transmission;
- least-privilege credentials stored outside tracked files;
- clear offline and privacy modes.

Do not enable passive surveillance, hidden recording, face recognition, location transmission, or cloud media retention without informed and explicit approval. Account for bystanders and local law.

## Safety Review Before Escalation

Before crossing a gate, restate:

1. the exact configuration;
2. evidence for voltage, current, polarity, driver, and mechanical limits;
3. the expected behavior;
4. the stop method;
5. the test duration and movement envelope;
6. what the user must inspect first;
7. what observation ends the test immediately.

For hazardous motion, also restate the independent physical stop, driver fail-safe state, supervisor/watchdog behavior, reset/re-arm sequence, and behavior after control-process failure.

If any critical evidence is missing, stop. Documentation, simulation, compilation, or retailer claims do not substitute for a safe physical configuration.
