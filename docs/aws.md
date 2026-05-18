# AWS Deployment Guide — Dudu Life Control

## Instance Details

| Property | Value |
|---|---|
| IP | `54.86.20.45` *(check AWS console — changes on restart)* |
| Region | `us-east-1` |
| OS | Amazon Linux 2023 |
| User | `ec2-user` |
| PEM key | `C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem` |

## Stack

| Layer | Tool |
|---|---|
| Runtime | Node.js v20 |
| Process manager | PM2 v6 (auto-restarts, survives reboots) |
| Reverse proxy | nginx 1.28 (port 80 + 443 → 3456) |
| SSL | Let's Encrypt via certbot (nip.io domain) |


---

## SSH into EC2

Use **Git Bash SSH** — Windows OpenSSH exits silently with code 255.

```bash
"C:\Program Files\Git\usr\bin\ssh.exe" \
  -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" \
  -o StrictHostKeyChecking=no \
  ec2-user@107.23.227.77
```

---

## Deploy a Code Change

Two deployment methods are available. Choose based on the project:

| Method | Best for |
|---|---|
| **SSH (direct)** | Node.js apps managed by PM2; no build step needed on the server |
| **GitHub Actions** | Projects with a `npm run build` step; `dist/` served by nginx directly |

### Option 1 — SSH (direct)

Run locally after pushing to `main`:

```bash
"C:\Program Files\Git\usr\bin\ssh.exe" \
  -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" \
  -o StrictHostKeyChecking=no \
  ec2-user@107.23.227.77 \
  "cd /home/ec2-user/<project_name> && git pull origin main && pm2 restart tinxy-ui && pm2 status"
```

### Option 2 — GitHub Actions

Workflow file: `.github/workflows/deploy.yml`

**How it works:**
1. Triggers automatically on push to `main` / `master`, or manually via `workflow_dispatch`.
2. Checks out code → `npm ci` → `npm run build`.
3. SCPs `dist/` to `/tmp/bse-deploy` on EC2 via `appleboy/scp-action`.
4. SSHs in, swaps build into `/var/www/bse-indicators`, fixes ownership (`nginx:nginx`), reloads nginx.

**Required GitHub Secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `EC2_HOST` | EC2 public IP (e.g. `54.86.20.45`) — update after any IP change |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | Full contents of `ec2-access.pem` (including header/footer lines) |

**Trigger manually:**
```bash
gh workflow run deploy.yml --repo <owner>/<repo>
# or: GitHub → Actions → Build & Deploy to EC2 → Run workflow
```

**Monitor a run:**
```bash
gh run list --workflow=deploy.yml --limit 5
gh run watch          # streams live logs for latest run
gh run view --log-failed   # show only failed steps
```

**If the deploy fails:** nginx logs are the first place to look:
```bash
"C:\Program Files\Git\usr\bin\ssh.exe" \
  -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" \
  -o StrictHostKeyChecking=no \
  ec2-user@107.23.227.77 \
  "sudo journalctl -u nginx -n 50 --no-pager"
```

> **Note:** when the EC2 IP changes, update the `EC2_HOST` secret in addition to the nginx/certbot steps below.

---

## EC2 Security Group

Security Group ID: `sg-0e31203d805a7239b` (default)

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | 0.0.0.0/0 | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP (nginx → HTTPS redirect) |
| 443 | TCP | 0.0.0.0/0 | HTTPS (nginx → app) |
| 8000 | TCP | 0.0.0.0/0 | Custom (pre-existing) |
| 8501 | TCP | 0.0.0.0/0 | Custom (pre-existing) |

---

## nginx Config

File: `/etc/nginx/conf.d/tinxy-ui.conf`

```nginx
server {
    listen 80;
    server_name 107-23-227-77.nip.io;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name 107-23-227-77.nip.io;

    ssl_certificate     /etc/letsencrypt/live/107-23-227-77.nip.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/107-23-227-77.nip.io/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:3456;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Reload nginx after editing:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## PM2 Commands

```bash
pm2 status                  # check app status
pm2 restart tinxy-ui        # restart app
pm2 logs tinxy-ui           # view logs
pm2 stop tinxy-ui           # stop app
pm2 start ecosystem.config.js  # start from config (first time)
```

PM2 config file: `/home/ec2-user/TinxyUI/ecosystem.config.js`

---

## SSL Certificate (Let's Encrypt)

- **Domain:** `107-23-227-77.nip.io` (nip.io maps IP → domain so Let's Encrypt works on raw IPs)
- **Cert path:** `/etc/letsencrypt/live/107-23-227-77.nip.io/`
- **Expires:** 2026-07-13 (auto-renews via certbot systemd timer)
- **Registered email:** `sac.khurana@gmail.com`

### If the EC2 IP changes — re-issue cert for new IP:

```bash
# 1. Get new cert (replace NEW_IP with actual IP, using hyphens)
sudo certbot --nginx -d NEW-IP-HERE.nip.io \
  --non-interactive --agree-tos \
  -m sac.khurana@gmail.com --redirect

# 2. Update nginx server_name and ssl paths manually if certbot can't auto-patch:
sudo nano /etc/nginx/conf.d/tinxy-ui.conf
# → change server_name and ssl_certificate paths to new domain

sudo nginx -t && sudo systemctl reload nginx
```

### Manual cert renewal:
```bash
sudo certbot renew --dry-run   # test renewal
sudo certbot renew             # force renew now
```

---

## First-Time Setup on a Fresh EC2 Instance

```bash
# 1. Install Node.js 20
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs

# 2. Install PM2
sudo npm install -g pm2

# 3. Install nginx
sudo dnf install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# 4. Install certbot
sudo dnf install -y certbot python3-certbot-nginx

# 5. Clone repo
cd /home/ec2-user
git clone https://github.com/sachin245/git file
cd TinxyUI

# 6. Start app with PM2
pm2 start ecosystem.config.js
pm2 save
pm2 startup   # follow the printed command to enable on reboot

# 7. Write nginx config (see nginx Config section above)
sudo nano /etc/nginx/conf.d/tinxy-ui.conf
sudo nginx -t && sudo systemctl reload nginx

# 8. Issue SSL cert (replace IP with actual)
sudo certbot --nginx -d i.p.ad.d \
  --non-interactive --agree-tos \
  -m sac.khurana@gmail.com --redirect
```

---

## Troubleshooting

| Problem | Command |
|---|---|
| App not responding | `pm2 logs program_name` |
| nginx error | `sudo journalctl -u nginx -n 50` |
| SSL cert error | `sudo certbot certificates` |
| Check what's on port 3456 | `sudo ss -tlnp \| grep 3456` |
| Restart everything | `pm2 restart program_name && sudo systemctl reload nginx` |
