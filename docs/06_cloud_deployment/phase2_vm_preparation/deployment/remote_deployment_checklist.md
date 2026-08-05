# Remote Deployment Checklist

## Before deployment

- Confirm official authorization to use the VM
- Record Ubuntu version, CPU, RAM, disk, IP address, and SSH user
- Confirm sudo and Docker installation permissions
- Confirm ports 22, 80, and 443
- Confirm PostgreSQL and MinIO ports will remain private
- Verify that the GitHub repository is accessible from the VM

## Repository preparation

- Clone the repository from GitHub
- Checkout the approved Phase II branch
- Verify the current commit hash
- Create the production environment file directly on the VM
- Never copy development passwords into the remote environment
- Generate new JWT, PostgreSQL, and MinIO secrets

## Docker preparation

- Install Docker Engine
- Install the Docker Compose plugin
- Add the authorized user to the docker group only when permitted
- Verify Docker and Compose versions
- Confirm sufficient free disk space

## Application deployment

- Build the production containers
- Start PostgreSQL and MinIO
- Run Alembic migrations
- Start the FastAPI backend
- Start Nginx
- Verify container health
- Verify the health endpoint through Nginx
- Verify administrator login and RBAC
- Verify PostgreSQL and MinIO are not publicly exposed

## Evidence to preserve

- Date and time of deployment
- VM configuration
- Git commit hash
- Docker and Compose versions
- Container status
- Health endpoint output
- Migration version
- Firewall status
- Screenshots and command logs

## Status rule

This checklist is preparation only. Items must not be marked completed until they are executed and verified on the authorized UESTC VM.
