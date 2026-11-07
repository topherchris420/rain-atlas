# BLACK GLASS firmware diff — ExampleOS-v1 → ExampleOS-v2

Protocol `blackglass.firmware-analysis/v1`, engine `0.1.0`.

**3 added, 2 removed, 2 changed** components; services +1/−1; network +3/−2.

## Noteworthy

- new declared ports: [1883]
- new services: ['systemd:mqtt.service']
- removed services: ['sysv:telnetd']

## Changed components

| path | kind | size Δ | imports + | imports − | needed + |
|---|---|---|---|---|---|
| etc/os-release | config | 0 | — | — | — |
| usr/sbin/httpd | elf | 32 | SSL_new | — | — |

## Added components

| path | kind |
|---|---|
| etc/mosquitto/mosquitto.conf | config |
| etc/systemd/system/mqtt.service | config |
| usr/sbin/mqttd | elf |

## Removed components

| path | kind |
|---|---|
| etc/init.d/telnetd | script |
| usr/sbin/telnetd | elf |

## Network surface changes

| Δ | component | kind | port |
|---|---|---|---|
| + | etc/mosquitto/mosquitto.conf | port-declared | 1883 |
| + | usr/sbin/httpd | socket-symbol | — |
| + | usr/sbin/mqttd | socket-symbol | — |
| − | usr/sbin/httpd | socket-symbol | — |
| − | usr/sbin/telnetd | socket-symbol | — |

