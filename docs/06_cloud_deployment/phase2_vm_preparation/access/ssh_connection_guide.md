# SSH Connection Preparation

## Information required before connection

- VM hostname or IP address: PENDING
- SSH username: PENDING
- SSH port: 22 unless otherwise specified
- Authentication method: SSH key preferred
- University firewall or VPN requirement: PENDING

## Recommended connection command

```powershell
ssh USERNAME@VM_IP
```

For a non-standard SSH port:

```powershell
ssh -p SSH_PORT USERNAME@VM_IP
```

## First-connection verification

After connecting, record the following commands and outputs:

```bash
hostname
whoami
cat /etc/os-release
nproc
free -h
df -h
ip addr
sudo -n true
```

## SSH key preparation

Generate a dedicated key only if required:

```powershell
ssh-keygen -t ed25519 -C "healthcare-platform-phase2"
```

Store the private key only on the authorized local computer. Send only the public key file ending in .pub to the university administrator.

## Security precautions

- Verify the server fingerprint with the university administrator before accepting it.
- Never commit private keys, passwords, access tokens, or real IP credentials to GitHub.
- Do not expose PostgreSQL or MinIO directly to the public network.
- Replace all PENDING placeholders only after official access is granted.
