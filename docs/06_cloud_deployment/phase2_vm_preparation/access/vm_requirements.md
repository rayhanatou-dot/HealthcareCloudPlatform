# UESTC VM Access Requirements

## Minimum technical requirements

- Operating system: Ubuntu Server 22.04 LTS or 24.04 LTS
- CPU: minimum 2 vCPU, recommended 4 vCPU
- Memory: minimum 4 GB RAM, recommended 8 GB
- Storage: minimum 50 GB
- Network: institutional or public IP address
- Access method: SSH
- Permissions: sudo access or permission to install and operate Docker
- Required software permission: Docker Engine and Docker Compose plugin

## Required network access

- Port 22: SSH administration
- Port 80: HTTP validation
- Port 443: HTTPS validation
- PostgreSQL port 5432 must remain internal
- MinIO API port 9000 must remain internal
- MinIO console must not be exposed publicly unless specifically authorized

## Information to request from the university

- VM IP address or hostname
- SSH username
- SSH port if different from 22
- Authentication method: SSH key or temporary password
- CPU allocation
- RAM allocation
- Storage capacity
- Ubuntu version
- Sudo permissions
- Firewall restrictions
- Authorized public ports
- VM usage period
- Responsible technical contact

## Security rule

No password, private SSH key, API token, or production secret must be committed to GitHub.
