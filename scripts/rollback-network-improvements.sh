#!/bin/bash
# Rollback script for network management improvements
# This script can restore the system to pre-improvement state

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

BACKUP_DIR="/opt/FPVCopilotSky/backups/network_improvements_$(date +%Y%m%d_%H%M%S)"
PROJECT_DIR="/opt/FPVCopilotSky"

echo -e "${BOLD}🔄 Network Improvements Rollback Script${NC}\n"

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run with sudo${NC}"
    exit 1
fi

# Function to create backup
create_backup() {
    echo -e "${YELLOW}📦 Creating backup of current files...${NC}"
    mkdir -p "$BACKUP_DIR"
    
    # Backup modified files
    cp -p "$PROJECT_DIR/app/services/network_service.py" "$BACKUP_DIR/" 2>/dev/null || true
    cp -p "$PROJECT_DIR/app/api/routes/network.py" "$BACKUP_DIR/" 2>/dev/null || true
    cp -p "$PROJECT_DIR/app/main.py" "$BACKUP_DIR/" 2>/dev/null || true
    cp -p "$PROJECT_DIR/scripts/setup-system-sudoers.sh" "$BACKUP_DIR/" 2>/dev/null || true
    
    echo -e "${GREEN}✅ Backup created in: $BACKUP_DIR${NC}\n"
}

# Function to check git status
check_git() {
    cd "$PROJECT_DIR"
    if [ -d .git ]; then
        echo -e "${YELLOW}📊 Git repository detected${NC}"
        echo ""
        git status --short
        echo ""
        return 0
    else
        echo -e "${YELLOW}⚠️  No git repository found${NC}\n"
        return 1
    fi
}

# Function to restore from git
restore_from_git() {
    echo -e "${YELLOW}🔄 Restoring files from git...${NC}"
    cd "$PROJECT_DIR"
    
    # List of files to restore
    FILES=(
        "app/services/network_service.py"
        "app/api/routes/network.py"
        "app/main.py"
        "scripts/setup-system-sudoers.sh"
    )
    
    for file in "${FILES[@]}"; do
        if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
            echo "  Restoring: $file"
            git checkout HEAD -- "$file"
        else
            echo "  Skipping: $file (not in git)"
        fi
    done
    
    echo -e "${GREEN}✅ Files restored from git${NC}\n"
}

# Function to disable auto-adjust without code changes
disable_auto_adjust() {
    echo -e "${YELLOW}🔧 Disabling auto-adjust feature...${NC}"
    
    # Comment out auto-adjust in main.py
    sed -i '/# Auto-adjust network priority every 30 seconds/,+6 s/^/# DISABLED: /' \
        "$PROJECT_DIR/app/main.py"
    
    echo -e "${GREEN}✅ Auto-adjust disabled${NC}\n"
}

# Function to restore old metrics manually
restore_old_metrics() {
    echo -e "${YELLOW}🔧 Restoring old metric values...${NC}"
    
    # This would require manual editing or having the old file
    # For safety, we'll just document what needs to be changed
    echo -e "${YELLOW}Manual changes needed in network_service.py:${NC}"
    echo "  METRIC_VPN = 10      → Remove this line"
    echo "  METRIC_PRIMARY = 100 → Change to 50"
    echo "  METRIC_SECONDARY = 200 → Change to 100"
    echo "  METRIC_TERTIARY = 600 → Keep as 600"
    echo ""
    echo -e "${YELLOW}Or restore from git if available.${NC}\n"
}

# Function to remove documentation
remove_docs() {
    echo -e "${YELLOW}🗑️  Removing new documentation...${NC}"
    
    rm -f "$PROJECT_DIR/docs/NETWORK_MANAGEMENT.md"
    rm -f "$PROJECT_DIR/docs/NETWORK_IMPROVEMENTS.md"
    rm -f "$PROJECT_DIR/docs/NETWORK_QUICKSTART.md"
    rm -f "$PROJECT_DIR/scripts/test-network-management.sh"
    
    echo -e "${GREEN}✅ Documentation removed${NC}\n"
}

# Function to restore sudoers
restore_sudoers() {
    echo -e "${YELLOW}🔧 Restoring sudoers file...${NC}"
    
    SUDOERS_FILE="/etc/sudoers.d/fpvcopilot-system"
    CURRENT_USER="${SUDO_USER:-fpvcopilotsky}"
    
    # Create sudoers without route commands
    cat > "$SUDOERS_FILE" << EOF
# Allow $CURRENT_USER to manage fpvcopilot-sky service without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/journalctl -u fpvcopilot-sky *

# Allow $CURRENT_USER to manage nginx service without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status nginx
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
EOF
    
    chmod 440 "$SUDOERS_FILE"
    
    if visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Sudoers restored (route commands removed)${NC}\n"
    else
        echo -e "${RED}❌ Error: Invalid sudoers syntax${NC}"
        return 1
    fi
}

# Function to restart service
restart_service() {
    echo -e "${YELLOW}🔄 Restarting fpvcopilot-sky service...${NC}"
    systemctl restart fpvcopilot-sky
    sleep 2
    
    if systemctl is-active --quiet fpvcopilot-sky; then
        echo -e "${GREEN}✅ Service restarted successfully${NC}\n"
    else
        echo -e "${RED}❌ Service failed to restart${NC}"
        echo "Check logs with: journalctl -u fpvcopilot-sky -n 50"
        return 1
    fi
}

# Main menu
show_menu() {
    echo -e "${BOLD}Select rollback option:${NC}"
    echo "1) Full rollback (git restore + disable features)"
    echo "2) Disable auto-adjust only (keep other improvements)"
    echo "3) Remove documentation only"
    echo "4) Restore sudoers (remove route permissions)"
    echo "5) Create backup only"
    echo "6) Show current git status"
    echo "7) Exit"
    echo ""
}

# Main execution
main() {
    while true; do
        show_menu
        read -p "Enter option [1-7]: " choice
        echo ""
        
        case $choice in
            1)
                echo -e "${BOLD}Option 1: Full Rollback${NC}\n"
                create_backup
                
                if check_git; then
                    read -p "Restore files from git? [y/N]: " confirm
                    if [[ $confirm == [yY] ]]; then
                        restore_from_git
                    else
                        echo "Skipping git restore"
                        disable_auto_adjust
                    fi
                else
                    echo -e "${YELLOW}Manual rollback required (no git found)${NC}"
                    restore_old_metrics
                    disable_auto_adjust
                fi
                
                remove_docs
                restore_sudoers
                restart_service
                
                echo -e "${GREEN}${BOLD}✅ Rollback completed!${NC}"
                break
                ;;
            2)
                echo -e "${BOLD}Option 2: Disable Auto-Adjust${NC}\n"
                create_backup
                disable_auto_adjust
                restart_service
                echo -e "${GREEN}${BOLD}✅ Auto-adjust disabled!${NC}"
                break
                ;;
            3)
                echo -e "${BOLD}Option 3: Remove Documentation${NC}\n"
                remove_docs
                echo -e "${GREEN}${BOLD}✅ Documentation removed!${NC}"
                break
                ;;
            4)
                echo -e "${BOLD}Option 4: Restore Sudoers${NC}\n"
                restore_sudoers
                echo -e "${GREEN}${BOLD}✅ Sudoers restored!${NC}"
                break
                ;;
            5)
                echo -e "${BOLD}Option 5: Create Backup${NC}\n"
                create_backup
                echo -e "${GREEN}${BOLD}✅ Backup created!${NC}"
                break
                ;;
            6)
                echo -e "${BOLD}Option 6: Git Status${NC}\n"
                check_git
                echo ""
                ;;
            7)
                echo -e "${YELLOW}Exiting without changes${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option. Please try again.${NC}\n"
                ;;
        esac
    done
}

# Show warning
echo -e "${YELLOW}⚠️  WARNING: This will rollback network management improvements${NC}"
echo -e "${YELLOW}   - VPN-aware routing will be disabled${NC}"
echo -e "${YELLOW}   - Auto-adjust feature will be removed${NC}"
echo -e "${YELLOW}   - Old metric values will be restored${NC}"
echo ""
read -p "Do you want to continue? [y/N]: " confirm

if [[ $confirm != [yY] ]]; then
    echo -e "${YELLOW}Rollback cancelled${NC}"
    exit 0
fi

echo ""
main

echo ""
echo -e "${BOLD}📋 Next Steps:${NC}"
echo "1. Verify service is running: sudo systemctl status fpvcopilot-sky"
echo "2. Check network status: curl http://localhost:8000/api/network/status"
echo "3. Restore backup if needed from: $BACKUP_DIR"
echo ""
echo -e "${GREEN}Done!${NC}"
