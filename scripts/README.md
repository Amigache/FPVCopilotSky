# Scripts Directory

This directory contains internal scripts used by FPVCopilotSky.

## 🎯 Recommended Usage

**Use the main CLI interface instead of running these scripts directly:**

```bash
cd /opt/FPVCopilotSky
./fpv
```

The `fpv` command provides a user-friendly menu to access all operations.

## 📁 Script Categories

### Installation & Deployment

- **deploy.sh** - Deploy to production (build frontend, install service)
- **install-production.sh** - Production-specific installation steps

### Development

- **dev.sh** - Start development mode with hot-reload

### Diagnostics & Status

- **status.sh** - Comprehensive system status check
- **preflight-check.sh** - Pre-flight verification (all dependencies)

### Configuration

- **configure-modem.sh** - USB modem configuration (4G/LTE)
- **setup-serial-ports.sh** - Serial port configuration for MAVLink
- **setup-sudoers.sh** - Unified sudo permissions setup
- **setup-system-sudoers.sh** - System-level sudoers (deprecated - use setup-sudoers.sh)
- **setup-tailscale-sudoers.sh** - Tailscale sudoers (deprecated - use setup-sudoers.sh)

### Testing

- **test-network-management.sh** - Network management system tests
- **test_network_features.sh** - Network feature tests

### Maintenance & Recovery

- **rollback-network-improvements.sh** - Emergency network rollback

## 🔧 Direct Script Usage

If you need to run scripts directly:

```bash
# Check system status
bash scripts/status.sh

# Deploy to production
sudo bash scripts/deploy.sh

# Start development mode
bash scripts/dev.sh

# Configure modem
sudo bash scripts/configure-modem.sh
```

## ⚠️ Important Notes

1. **Most scripts require sudo** - They modify system configuration
2. **setup-sudoers.sh is the unified sudoers file** - Old split files are deprecated
3. **Always run from project root** - Scripts expect `/opt/FPVCopilotSky` as working directory
4. **Use the CLI for better UX** - The `fpv` command provides guided operations

## 📝 Adding New Scripts

When adding new scripts:

1. Place them in this directory
2. Add them to the `fpv` CLI menu
3. Document them in this README
4. Make them executable: `chmod +x scripts/your-script.sh`
