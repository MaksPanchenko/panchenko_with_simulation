> Справка по ROS/MSP и ручному запуску. Автоматический запуск описан в [README](../README.md).

# MultiWii / Cleanflight / Betaflight bridge for ROS 2

C++17 ROS 2 port of [ros-multiwii](https://github.com/christianrauch/ros-multiwii),
with controller-reported arm/disarm state and flight mode. Package: `multiwii`;
node: `multiwii_node`. ROS 2 Humble on Ubuntu 22.04 or Jazzy on Ubuntu 24.04;
Linux amd64/arm64.
The class declaration is in `include/multiwii/multiwii_node.hpp`, the implementation
in `src/multiwii_node.cpp`, and the executable entry point in `src/main.cpp`.
The serial bridge and the included MSP emulator are both C++17. Python is used
only for ROS launch files and test/installation tools.

The directory is a complete source package: driver, interfaces, configuration,
bundled MSP library, tests, and ARM64 QEMU tooling. No sibling repository,
Gazebo installation, global MSP library, or prebuilt binary is required.

## Build

Run from the directory containing `package.xml`. The script installs ROS 2 and
the build dependencies for the host OS; the first setup needs internet and sudo.

```bash
./scripts/build.sh
source /opt/ros/"$(cat .runtime/ros-distro)"/setup.bash
source install/setup.bash
```

Build only this directory if sibling copies of the `multiwii` package exist;
do not run unrestricted package discovery from their common parent.
`third_party/msp` contains the pinned library sources and license; CMake does
not download dependencies. For a runtime-only build use `-DBUILD_TESTING=OFF`.

## Launch the complete demo

```bash
./scripts/run.sh
# Equivalent after sourcing the workspace:
ros2 launch multiwii system.launch.py
```

The launch file starts the C++ MSP controller emulator, waits for its PTY to be
ready, then starts the real serial driver. It cycles every three seconds through
`DISARMED/ACRO`, `ARMED/ANGLE`, `ARMED/HORIZON`, and `DISARMED/FAILSAFE`.
These are scripted controller responses, not a flight dynamics simulation.
The emulator acknowledges control commands but does not change its scripted
state in response to them. `Ctrl+C` stops both processes; either process exiting
also shuts down the launch. No fixed PTY path, TCP port, or startup sleep is used.

In another terminal, source ROS and `install/setup.bash`, then inspect:

```bash
ros2 topic echo /multiwii/armed
ros2 topic echo /multiwii/flight_mode
ros2 topic echo /multiwii/state
ros2 topic hz /multiwii/imu/data
```

## Connect a real controller

Enable MSP on the controller's serial port and use the matching baud rate:

```bash
./scripts/run.sh mode:=hardware device:=/dev/ttyACM0 baudrate:=115200
# Optional alternate calibration/rates:
./scripts/run.sh mode:=hardware device:=/dev/ttyUSB0 config:="$PWD/cfg/sbc.yaml"
```

The user needs serial-device access (usually membership in `dialout`, followed
by a new login). No ROS MAVROS node, MAVLink, Gazebo, or emulator runs in hardware
mode. The node observes the controller's ARM flag; it does not automatically arm
the controller. Existing RC and motor input topics remain available.

Supported contract: MSP v1-compatible firmware advertising `MSP_FC_VARIANT`,
`MSP_BOXNAMES`, `MSP_BOXIDS`, and the 11-byte `MSP_STATUS` base. MultiWii,
Cleanflight, and Betaflight-style status layouts are handled; firmware-specific
INAV layouts and modes outside the first 32 status bits are not implemented.
Mode tables are read at connection time. Restart after changing the controller's
enabled features/mode table or losing the serial device; automatic reconnection
is not implemented.

## Topics and interpretation

All names below are relative to `/multiwii`.

| Topic | Type | Meaning |
|---|---|---|
| `armed` | `std_msgs/msg/Bool` | `true` = controller reports armed; `false` = disarmed |
| `flight_mode` | `std_msgs/msg/String` | Primary displayed mode; `UNKNOWN` when status is stale |
| `state` | `mavros_msgs/msg/State` | Same arm/mode observation with timestamp and connection validity |
| `imu/data` | `sensor_msgs/msg/Imu` | Acceleration m/s², angular rate rad/s, estimated orientation |
| `imu/mag` | `sensor_msgs/msg/MagneticField` | Magnetic field in tesla |
| `local_position/pose` | `geometry_msgs/msg/PoseStamped` | Attitude of `multiwii` in `multiwii_cartesian`; position is zero |
| `rpy` | `geometry_msgs/msg/Vector3` | Roll, pitch, yaw in degrees |
| `rc/in` | `mavros_msgs/msg/RCIn` | Received RC channels |
| `rc/servo`, `motors` | `mavros_msgs/msg/RCOut` | Servo/motor values |
| `battery` | `sensor_msgs/msg/BatteryState` | Voltage and current from MSP_ANALOG |
| `global_position/compass_hdg` | `std_msgs/msg/Float64` | Magnetometer heading in degrees |
| `global_position/rel_alt`, `global_position/sonar_alt` | `std_msgs/msg/Float64` | Altitude in metres |
| `rc/override`, `rc/override/raw` | `mavros_msgs/msg/OverrideRCIn` | Input: remapped RPYT/AUX or controller-native channel order |
| `actuator_control` | `mavros_msgs/msg/ActuatorControl` | Input: eight motor controls; magnitude in [0,1] maps to [1000,2000] |

`MSP_STATUS` is polled at 5 Hz by default. ARM and modes come from received
status flags, not outgoing RC values. On Cleanflight/Betaflight a status bit is
the **position in the advertised box list**, not a permanent box ID. Classic
MultiWii's permanent-ID layout is handled separately.

Several mode flags can be active simultaneously. The display priority is
`FAILSAFE > GPS RESCUE > GPS HOME > GPS HOLD > PASSTHRU > HORIZON > ANGLE > ACRO`.
Auxiliary boxes such as ARM and BEEPER do not select the flight mode. `ACRO`
means none of these primary mode flags is active and can be reported while
disarmed. Other firmware-specific mode names need an explicit policy extension.

The three state publishers use reliable, volatile, keep-last-1 QoS. They publish
on each valid status response. After `status_timeout` (2 seconds by default),
`state.connected=false` and `flight_mode=UNKNOWN`; **no fabricated disarm is
published**. `state.armed` and its timestamp retain the last valid observation;
consumers must check `connected`. Before the first response the state timestamp
is zero. `guided`, `manual_input`, and `system_status` are not populated by MSP.
Use `state` for a timestamped, internally consistent observation of arm and mode.

TF: `map -> multiwii_cartesian -> multiwii`, with barometric altitude and attitude.
Sonar does not overwrite the barometric TF. IMU calibration in `cfg/sbc.yaml`
must match the controller's raw scales. If acceleration/magnetic vectors cannot
define orientation, `orientation_covariance[0]=-1` marks it unavailable.

`MSPRawMessage` and two raw service **definitions** are generated; no raw service servers or new arming service are provided.

## Parameters and SBC operation

`cfg/sbc.yaml` provides moderate polling rates for a 115200-baud serial link:
IMU/attitude 50 Hz, altitude/RC/motors 10 Hz, status 5 Hz, servo/battery 1 Hz.
Sonar is disabled by default. Each `MSP_*` rate is a floating-point number in Hz;
zero stops polling. Rates can be changed at runtime:

```bash
ros2 param set /multiwii MSP_STATUS 10.0
ros2 param set /multiwii MSP_RAW_IMU 0.0
ros2 param set /multiwii MSP_RAW_IMU 50.0
```

Invalid/non-finite rates and invalid atomic parameter batches are rejected.
Maximums: RC/servo/battery 100 Hz, other supported polls 1000 Hz. These are input
limits, not achievable rates on every serial link. Device, baud rate, calibration, frame, and
timeout parameters require a node restart. Keep the timeout longer than the
status polling interval. The link watchdog uses monotonic wall time.

For Orange Pi 5 or Raspberry Pi 5 use a 64-bit OS and arm64 ROS 2 libraries,
build in Release, and start with the SBC polling profile. No x86-only flags or
GUI dependencies are used. The board's kernel/USB/UART support must come from
its OS vendor. The setup script selects Humble for Ubuntu 22.04 and Jazzy for
Ubuntu 24.04; both run natively on arm64.
QEMU validation below checks ARM64 userspace execution; it does not model Pi 5
GPIO, UART hardware timing, or flight-control performance.

## Automated checks

```bash
./scripts/test.sh
source install/setup.bash
python3 scripts/test-launch.py
```

The first command runs C++ status tests and an end-to-end ROS/PTY test, including
all telemetry, mode decoding, malformed status, loss/recovery, runtime rate
changes, atomic rejection, RC remapping, motor commands, and SIGINT shutdown.
The second starts the complete launch, observes its scripted states, and checks
shutdown. Test domains default to 73/74; set `ROS_DOMAIN_ID` if needed.
Logs are under `.runtime/` and CTest results under `build/multiwii/test_results/`.

## ARM64 emulation on an x86 computer

QEMU's [generic `virt` board](https://www.qemu.org/docs/master/system/arm/virt.html)
runs Ubuntu ARM64 with software CPU emulation (TCG). It is used to validate the
same architecture/userspace as a 64-bit SBC, rather than reproduce Pi-specific
peripherals. The ROS driver and MSP emulator run together inside the guest;
no host-to-guest ROS networking or Gazebo connection is needed.

On the host:

```bash
./scripts/setup.sh qemu
./emulation/prepare.sh
./emulation/start.sh
```

Preparation downloads the Ubuntu Jammy ARM64 cloud image, verifies its SHA256,
creates a 20 GB disk, and provisions an SSH-key-only `reviewer` user. All disk
images, SSH keys, and VM state stay in `.runtime/qemu/` and are ignored by Git.
Alternatively use `prepare.sh --image /path/to/jammy-arm64.img`, or
`prepare.sh --reuse /path/to/existing-jammy-arm64-disk.qcow2` to **copy and flatten**
an existing guest. Existing files are read only. Do not copy a running VM disk.

Wait for the guest to boot (TCG may take several minutes). In another host terminal:

```bash
./emulation/ssh.sh 'uname -m; dpkg --print-architecture'
# Expected: aarch64, arm64
./emulation/copy-source.sh
./emulation/ssh.sh
```

Inside the guest:

```bash
cd ~/temporary
./emulation/guest-setup.sh   # installs ROS and build dependencies; requires internet
./scripts/build.sh -DMULTIWII_EMULATION_BUILD=ON
./scripts/test.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 scripts/test-launch.py
./scripts/run.sh            # optional interactive demo; Ctrl+C stops it
```

`MULTIWII_EMULATION_BUILD=ON` disables optimization for the ROS node to shorten
compilation under TCG. It uses the same source, interfaces, and tests. For the
optimized SBC build, omit the option in a fresh build directory or pass
`-DMULTIWII_EMULATION_BUILD=OFF`. Emulation is a functional compatibility check;
performance should be measured on the target SBC with optimization enabled.

The default VM has two Cortex-A72 virtual CPUs and 3 GB RAM. Override `VM_CPUS`,
`VM_MEMORY` (MiB), or `VM_SSH_PORT` (default 2233, localhost only) when launching;
use the same port for `ssh.sh`/`copy-source.sh`. Stop cleanly with
`./emulation/ssh.sh 'sudo poweroff'` on the host. `start.sh` reuses the saved disk.
The VM has outbound networking for apt; DDS remains inside the guest.

