# Stage 8: backup and restore

`mariyam-backup.sh` makes a PostgreSQL custom-format dump without writes, archives the
canonical profile `config.yaml`/`SOUL.md` and `/opt/hermes-mariyam-secrets`, encrypts
the single payload with AES-256 GPG, uploads it to
`hermes_mariyam_gdrive:hermes-mariyam-backups`, and retains the newest 30 archives.

On the VPS, once only, create the encryption secret without printing it:

```bash
umask 077
openssl rand -base64 48 > /opt/hermes-mariyam-secrets/backup-gpg-passphrase
chmod 600 /opt/hermes-mariyam-secrets/backup-gpg-passphrase
sudo install -m 644 deploy/backup/mariyam-backup.service /etc/systemd/system/
sudo install -m 644 deploy/backup/mariyam-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mariyam-backup.timer
```

Install heartbeat units as well:

```bash
sudo install -m 644 deploy/backup/mariyam-heartbeat.service /etc/systemd/system/
sudo install -m 644 deploy/backup/mariyam-heartbeat.timer /etc/systemd/system/
sudo install -m 644 deploy/backup/mariyam-heartbeat-failure@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mariyam-heartbeat.timer
```

Run a first backup with `sudo systemctl start mariyam-backup.service`. Check only
metadata with `cat /opt/hermes-mariyam/var/backup/last-backup.json` and
`systemctl status mariyam-backup.service`. Restore verification is always disposable:

```bash
/opt/hermes-mariyam/deploy/backup/mariyam-restore-check.sh
```

The checker decrypts into a private temporary directory, restores into a uniquely
named temporary PostgreSQL container, compares every table count and a known expense,
checks canonical profile files, and removes the container. It never accepts a
production database target.
