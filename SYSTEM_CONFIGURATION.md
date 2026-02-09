# System Configuration Changes

Este documento describe todos los cambios realizados a nivel de sistema durante la instalación y operación de FPV Copilot Sky.

## 📋 Overview

FPV Copilot Sky requiere configuraciones específicas del sistema para funcionamiento completo. Estas se aplican automáticamente durante `install.sh` y se pueden verificar con `scripts/status.sh`.

---

## 🔧 Configuraciones Modificadas

### 1. NetworkManager Configuration

**Archivo**: `/etc/NetworkManager/NetworkManager.conf`

```ini
[ifupdown]
managed=true  # Cambió de: managed=false
```

**Propósito**: Permite que NetworkManager gestione todas las interfaces de red (WiFi, Ethernet, etc.)

**Verificación**:

```bash
grep "managed=" /etc/NetworkManager/NetworkManager.conf
```

**Status Check**: `✅ NetworkManager configured to manage interfaces`

---

### 2. Netplan WiFi Configuration

**Archivo**: `/etc/netplan/30-wifis-dhcp.yaml`

```yaml
network:
  version: 2
  renderer: NetworkManager # Cambió de: renderer: networkd
  wifis:
    wlan0:
      dhcp4: true
      dhcp6: true
      access-points:
        "SSID":
          password: "password"
```

**Propósito**: Delega la gestión de WiFi a NetworkManager en lugar de systemd-networkd, permitiendo escaneo y conexión dinámicos.

**Verificación**:

```bash
grep "renderer:" /etc/netplan/30-wifis-dhcp.yaml
```

**Status Check**: `✅ Netplan WiFi using NetworkManager renderer`

**Nota**: Si esta línea dice `renderer: networkd`, el escaneo de WiFi no funcionará. Ejecutar:

```bash
sudo sed -i 's/renderer: networkd/renderer: NetworkManager/' /etc/netplan/30-wifis-dhcp.yaml
sudo netplan apply
sudo nmcli dev set wlan0 managed yes
```

---

### 3. WiFi Interface Management

**Comando**: `nmcli dev set wlan0 managed yes`

**Propósito**: Asegura que wlan0 es gestionada por NetworkManager

**Verificación**:

```bash
nmcli dev status | grep wlan0
# Debe mostrar: "connected" o "disconnected", NO "unmanaged"
```

**Status Check**: `wlan0 state: connected` (o similar, pero NO "unmanaged")

---

## 🔐 Sudo Permissions (sin contraseña)

### WiFi Management

**Archivo**: `/etc/sudoers.d/fpvcopilot-wifi`

```bash
# FPV Copilot Sky - WiFi management permissions
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/iw dev * scan
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli device wifi connect *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli device wifi disconnect
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli connection up *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli connection down *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli dev wifi rescan
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/nmcli dev set * managed *
```

**Propósito**: Permite que el proceso fpvcopilot-sky ejecute comandos WiFi sin solicitar contraseña

**Verificación**:

```bash
sudo -l -U fpvcopilotsky | grep -i wifi
```

**Status Check**: `✓ WiFi scan commands work without password`

### Tailscale VPN

**Archivo**: `/etc/sudoers.d/tailscale`

```bash
# Allow user to manage Tailscale without password
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale up
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale up *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale down
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale logout
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale status
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale status *
```

**Propósito**: Gestión automatizada de VPN

**Status Check**: `✓ Tailscale sudoers file exists`

### System Management

**Archivo**: `/etc/sudoers.d/fpvcopilot-system`

Controla restart, stop, logs del servicio sin contraseña

**Status Check**: `✓ System management sudoers file exists`

---

## 🔧 Kernel Parameters (Sysctl)

**Archivo**: `/etc/sysctl.d/99-fpv-streaming.conf`

### TCP Buffer Optimization

```sysctl
net.core.rmem_max=134217728           # 128MB read buffer
net.core.wmem_max=134217728           # 128MB write buffer
net.core.rmem_default=1048576         # 1MB default
net.core.wmem_default=1048576         # 1MB default
net.ipv4.tcp_rmem=4096 1048576 134217728
net.ipv4.tcp_wmem=4096 1048576 134217728
```

**Propósito**: Optimizado para streaming de video sobre LTE/4G

### UDP Optimization

```sysctl
net.ipv4.udp_rmem_min=65536
net.ipv4.udp_wmem_min=65536
```

### BBR Congestion Control

```sysctl
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr   # Mejor para ancho de banda variable (4G)
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_mtu_probing=1
```

### Network Backlog

```sysctl
net.core.netdev_max_backlog=5000
net.core.somaxconn=4096
```

### Memory Management

```sysctl
vm.swappiness=10  # Preferir RAM sobre swap
```

**Verificación**:

```bash
sysctl net.ipv4.tcp_congestion_control  # Debe mostrar: bbr
```

---

## 🌐 Network Services

### NetworkManager

**Estado**: Enabled and started

```bash
sudo systemctl status NetworkManager
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager
```

**Propósito**: Gestión centralizada de interfaces de red

### ModemManager

**Estado**: Enabled and started

```bash
sudo systemctl status ModemManager
sudo systemctl enable ModemManager
sudo systemctl start ModemManager
```

**Propósito**: Gestión de módems USB (Huawei E3372h, etc.)

---

## 📱 USB Modem Configuration

**Archivo**: `/etc/usb_modeswitch.d/12d1:1f01`

Configuración automática para Huawei modems en modo almacenamiento

**Propósito**: Convertir modem USB de modo almacenamiento a modo modem

**Verificación**:

```bash
lsusb | grep -i huawei
# Debe mostrar: 12d1:14dc (modo modem) NO 12d1:1f01 (modo almacenamiento)
```

---

## 🚀 Service Configuration

**Archivo**: `/etc/systemd/system/fpvcopilot-sky.service`

```ini
[Service]
Type=simple
User=fpvcopilotsky
Group=fpvcopilotsky
SupplementaryGroups=dialout video netdev  # Acceso a puertos seriales y wifi
```

**Propósito**: Ejecutar el backend con permisos adecuados para red y video

---

## ✅ Verifications

### Usar status.sh

El script `scripts/status.sh` verifica automáticamente todos los cambios:

```bash
cd /opt/FPVCopilotSky
bash scripts/status.sh
```

### Outputs esperados

```
✅ nmcli (NetworkManager CLI) working
✅ WiFi scanning works (X networks detected)
✅ NetworkManager configured to manage interfaces
✓ WiFi management sudoers file exists
✓ WiFi scan commands work without password
```

---

## 🔧 Troubleshooting

### WiFi scanning no funciona

1. **Problema**: `wlan0 state: unmanaged`

   **Solución**:

   ```bash
   sudo sed -i 's/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf
   sudo systemctl restart NetworkManager
   sudo nmcli dev set wlan0 managed yes
   ```

2. **Problema**: `renderer: networkd` en netplan

   **Solución**:

   ```bash
   sudo sed -i 's/renderer: networkd/renderer: NetworkManager/' /etc/netplan/30-wifis-dhcp.yaml
   sudo netplan apply
   ```

3. **Problema**: Permisos sudo insuficientes

   **Solución**: Re-ejecutar install.sh

   ```bash
   cd /opt/FPVCopilotSky
   bash install.sh
   ```

### Conexión de red lenta para video

- Verificar buffers TCP: `sysctl net.ipv4.tcp_rmem`
- Verificar congestion control: `sysctl net.ipv4.tcp_congestion_control` (debe ser `bbr`)
- Habilitar Flight Mode en la UI para aplicar optimizaciones adicionales

---

## 📝 Resumen de Cambios

| Componente      | Archivo                                      | Cambio                                  | Propósito                   |
| --------------- | -------------------------------------------- | --------------------------------------- | --------------------------- |
| NetworkManager  | `/etc/NetworkManager/NetworkManager.conf`    | `managed=false` → `managed=true`        | Gestionar interfaces de red |
| Netplan WiFi    | `/etc/netplan/30-wifis-dhcp.yaml`            | `renderer: networkd` → `NetworkManager` | WiFi scan dinámico          |
| WiFi Management | `/etc/sudoers.d/fpvcopilot-wifi`             | Creado                                  | WiFi sin contraseña         |
| Kernel          | `/etc/sysctl.d/99-fpv-streaming.conf`        | Creado                                  | Optimización 4G/LTE         |
| Service         | `/etc/systemd/system/fpvcopilot-sky.service` | SupplementaryGroups                     | Acceso a red/video          |

---

## 🔍 Monitoreo Continuo

Ver status completo en todo momento:

```bash
# Verificación rápida
bash scripts/status.sh

# Logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Estado de red
nmcli dev status
nmcli connection show

# Escaneo WiFi manual
sudo iw dev wlan0 scan | grep SSID
```

---

**Última actualización**: Febrero 9, 2026
**Versión**: 1.0.0
