# Deploying the AI Doctor backend to AWS

This runbook takes you from a fresh AWS account to a running HTTPS API at
`https://api.diegojrobles.com`. It assumes no prior AWS knowledge. Every step
says what you are doing and why.

Only the backend is deployed. The Expo frontend is not.

---

## What you are building

```
        iPhone / curl
             |  HTTPS (port 443)
             v
   +---------------------------+
   |   EC2 instance (one box)  |
   |                           |
   |   [Caddy]   <- TLS cert   |
   |      |                    |
   |   [FastAPI app]           |
   |      |                    |
   |   [Postgres] -> EBS disk  |
   +---------------------------+
             ^
             |  secrets read at container start
        SSM Parameter Store
```

- **Caddy** terminates HTTPS and gets a free Let's Encrypt certificate
  automatically. iOS App Transport Security rejects plain HTTP, so this is
  required, not optional.
- **FastAPI** is the application. It is never exposed to the internet directly.
- **Postgres** stores users and symptom data on a disk that survives reboots.
- **SSM Parameter Store** holds your API keys, encrypted. The instance reads
  them at startup using its IAM role, so no secret is ever written to disk or
  baked into the image.

---

## Prerequisites

- An AWS account
- A terminal on your laptop
- Control of the DNS for `diegojrobles.com`
- An OpenRouter API key
- A Pinecone API key **and an existing, populated index** (see
  [Known issues](#known-issues) — retrieval is currently broken without this)

---

## Step 0 — Rotate the leaked OpenRouter key

**Do this before anything else.**

The file `server/.env` was committed in this repository's first commit
(`215198cd`) and is still present in git history on the public GitHub remote.
Removing a file from the current tree does not remove it from history. The key
is readable by anyone.

1. Go to <https://openrouter.ai/keys>
2. **Revoke** the existing key. Do not merely create a second one.
3. Create a new key. You will store it in SSM in Step 6.

Optionally, scrub history afterwards with `git filter-repo` and force-push.
That is good hygiene, but it does **not** un-leak the key — only revocation does.

---

## Step 1 — Install the AWS CLI and create a robot user

The AWS CLI is how your laptop sends commands to AWS.

```bash
brew install awscli
aws --version
```

Now create an **IAM user** — a separate login for automation, so that if its
key leaks you delete one robot instead of losing your whole account.

1. Sign in to the AWS Console as root.
2. Go to **IAM → Users → Create user**. Name it `deploy-admin`.
3. Select **Attach policies directly** → check **AdministratorAccess**.
   (Narrower permissions are better practice; admin keeps this runbook short.
   Delete this user when you are done — see [Teardown](#teardown).)
4. Create the user, then open it → **Security credentials** → **Create access key**
   → **Command Line Interface (CLI)**.
5. Copy the Access key ID and Secret access key.

Configure the CLI. Paste the keys when prompted — they go into
`~/.aws/credentials` on your machine and nowhere else:

```bash
aws configure
```

Set the region to `us-east-1` and output to `json`. Verify:

```bash
aws sts get-caller-identity
```

You should see your account number.

---

## Step 2 — Set budget alarms BEFORE creating anything billable

AWS bills by the hour and will not warn you on its own. Do this now, while your
spend is still zero — an alarm added after a runaway resource is useless.

Run this in your **local terminal**. Paste the whole block at once and press
Enter; it will prompt for your email, then create both alarms.

> The `cat > file <<EOF ... EOF` pattern is not a normal command — it means
> "write everything up to the line `EOF` into that file." That is why the block
> has to be pasted as a unit rather than line by line.

> Note: this uses `printf` + `read` rather than bash's `read -p`. macOS defaults
> to zsh, where `-p` means "read from a coprocess" and fails with
> `read: -p: no coprocess`, leaving the email empty.

```bash
printf "Your email for budget alerts: "; read ALERT_EMAIL
[ -z "$ALERT_EMAIL" ] && echo "ERROR: no email entered, stopping." && return 2>/dev/null || true

ACCT=$(aws sts get-caller-identity --query Account --output text)
echo "Account: $ACCT / Email: $ALERT_EMAIL"

for AMT in 5 15; do
  cat > /tmp/budget-$AMT.json <<EOF
{
  "BudgetName": "aidoctor-${AMT}-dollar",
  "BudgetLimit": {"Amount": "${AMT}", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF
  cat > /tmp/notify-$AMT.json <<EOF
[{
  "Notification": {
    "NotificationType": "ACTUAL",
    "ComparisonOperator": "GREATER_THAN",
    "Threshold": 100,
    "ThresholdType": "PERCENTAGE"
  },
  "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "${ALERT_EMAIL}"}]
}]
EOF
  aws budgets create-budget \
    --account-id "$ACCT" \
    --budget file:///tmp/budget-$AMT.json \
    --notifications-with-subscribers file:///tmp/notify-$AMT.json \
    && echo "created \$${AMT} budget"
done
```

**AWS will email you to confirm the subscription. Click the link in that email,
or the alerts will never fire.**

Confirm both exist:

```bash
aws budgets describe-budgets \
  --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --query 'Budgets[].BudgetName'
```

---

## Step 3 — Store your secrets in SSM Parameter Store

These are stored encrypted. The EC2 instance will read them at startup.
**Type these in your own terminal** — the values should not be pasted into chat
logs or committed anywhere.

```bash
# Your new OpenRouter key from Step 0
aws ssm put-parameter --name /aidoctor/prod/OPENROUTER_API_KEY \
  --value 'sk-or-v1-REPLACE-ME' --type SecureString --overwrite

# Your Pinecone key
aws ssm put-parameter --name /aidoctor/prod/PINECONE_API_KEY \
  --value 'pcsk_REPLACE-ME' --type SecureString --overwrite

aws ssm put-parameter --name /aidoctor/prod/PINECONE_INDEX_NAME \
  --value 'medical-knowledge' --type SecureString --overwrite

# A random database password. This generates one; you never need to see it.
aws ssm put-parameter --name /aidoctor/prod/POSTGRES_PASSWORD \
  --value "$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)" \
  --type SecureString --overwrite

# A random signing key for JWT session tokens.
aws ssm put-parameter --name /aidoctor/prod/SECRET_KEY \
  --value "$(openssl rand -hex 32)" --type SecureString --overwrite
```

Verify the names (this prints names only, not values):

```bash
aws ssm get-parameters-by-path --path /aidoctor/prod/ --query 'Parameters[].Name'
```

Standard-tier parameters are free.

---

## Step 4 — Create the IAM role that lets the instance read those secrets

The instance needs permission to read SSM. An **instance role** grants that
without putting any access key on the box.

```bash
cat > /tmp/trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role --role-name aidoctor-instance-role \
  --assume-role-policy-document file:///tmp/trust.json

cat > /tmp/ssm-read.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
    "Resource": "arn:aws:ssm:*:*:parameter/aidoctor/prod/*"
  }, {
    "Effect": "Allow",
    "Action": "kms:Decrypt",
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy --role-name aidoctor-instance-role \
  --policy-name aidoctor-ssm-read --policy-document file:///tmp/ssm-read.json

aws iam create-instance-profile --instance-profile-name aidoctor-instance-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name aidoctor-instance-profile \
  --role-name aidoctor-instance-role
```

Note the policy is scoped to `/aidoctor/prod/*`. The instance can read its own
secrets and nothing else in your account.

---

## Step 5 — Create the firewall rule and launch the server

A **security group** is a firewall. Open only ports 22 (SSH), 80 (needed for
the certificate check), and 443 (HTTPS).

```bash
SG_ID=$(aws ec2 create-security-group \
  --group-name aidoctor-sg \
  --description "AI Doctor backend" \
  --query 'GroupId' --output text)
echo "Security group: $SG_ID"

# Restrict SSH to your own IP only.
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr "${MY_IP}/32"

aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0
```

Create an SSH key so you can log in:

```bash
aws ec2 create-key-pair --key-name aidoctor-key \
  --query 'KeyMaterial' --output text > ~/.ssh/aidoctor-key.pem
chmod 400 ~/.ssh/aidoctor-key.pem
```

Launch the instance. `t4g.micro` is an ARM instance — the cheapest option that
comfortably runs this stack.

```bash
AMI_ID=$(aws ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
  --query 'Parameter.Value' --output text)

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t4g.micro \
  --key-name aidoctor-key \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name=aidoctor-instance-profile \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=aidoctor}]' \
  --query 'Instances[0].InstanceId' --output text)
echo "Instance: $INSTANCE_ID"
```

Give it a fixed public address. Without this, a reboot changes the IP and breaks
your DNS.

```bash
ALLOC_ID=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID"

PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)
echo "Your server IP is: $PUBLIC_IP"
```

**Write down `$INSTANCE_ID`, `$ALLOC_ID`, `$SG_ID`, and `$PUBLIC_IP`.** You need
them for teardown.

---

## Step 6 — Point your domain at the server

At your DNS provider for `diegojrobles.com`, create one record:

| Field | Value |
|---|---|
| Type | `A` |
| Name / Host | `api` — just this, **not** `api.diegojrobles.com` |
| Value | the `$PUBLIC_IP` from Step 5 |
| TTL | 300, or the lowest the provider allows |

Most providers append the domain automatically, so entering the full hostname
in the Host field creates `api.diegojrobles.com.diegojrobles.com`.

### If your DNS is at Network Solutions

This domain's nameservers are `ns23`/`ns24.worldnic.com`, which is Network
Solutions. The root `@` and `www` records point at GitHub Pages for the
portfolio site — **do not edit or delete them.** You are adding one new row.

1. Sign in at networksolutions.com → **Account Manager**
2. **My Domain Names** → `diegojrobles.com` → **Manage**
3. **Change Where Domain Points** → **Advanced DNS**
   (or **Manage Advanced DNS Records**)
4. **A records (Host)** section → **Edit** / **Add A Record**
5. Use an empty row. Host `api`, IP address = your Elastic IP.
6. Save — there may be two confirmation screens.

Do **not** use "Domain Forwarding" or "Masking". Those are HTTP redirects, not
DNS records; Let's Encrypt cannot validate against them and iOS will reject the
result. It must be an A record.

Worldnic propagation is slow — allow 30 minutes, sometimes a few hours.

**This must be done before the next step.** Let's Encrypt proves you own the
domain by connecting to whatever `api.diegojrobles.com` resolves to. No DNS,
no certificate.

Wait for it to propagate, then confirm it returns your IP — check a public
resolver too, in case your machine cached the earlier empty answer:

```bash
dig +short A api.diegojrobles.com
dig +short A api.diegojrobles.com @8.8.8.8
```

**Do not run `deploy.sh` until both return your Elastic IP.** Caddy requests a
certificate on first start, and repeated Let's Encrypt failures trigger a rate
limit that locks you out for hours.

---

## Step 7 — Install Docker on the server and deploy

SSH in:

```bash
ssh -i ~/.ssh/aidoctor-key.pem ubuntu@api.diegojrobles.com
```

Install Docker:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
newgrp docker
```

Install the AWS CLI. Ubuntu 24.04 dropped the `awscli` apt package — `apt install
awscli` fails with "no installation candidate". Use snap:

```bash
sudo snap install aws-cli --classic
```

If snap is unavailable, use the official installer. `t4g` instances are ARM, so
the URL must be the `aarch64` build — confirm with `uname -m`:

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install && rm -rf awscliv2.zip aws
```

Verify everything is present:

```bash
aws --version; docker --version; docker compose version
```

You do **not** run `aws configure` here. The instance authenticates through its
IAM role. Confirm that works — this is also the check that the instance profile
attached correctly:

```bash
aws ssm get-parameters-by-path --path /aidoctor/prod/ --query 'Parameters[].Name'
```

It should list all five parameter names. A permissions error here means
`deploy.sh` will fail at container start.

1GB of RAM is snug with Postgres. Add swap so the kernel does not kill a
container under a memory spike:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Clone the repository and configure:

```bash
git clone https://github.com/diegojrobles/AI-Doctor-Chatbot-v2.git
cd AI-Doctor-Chatbot-v2
cp deploy.env.example deploy.env
nano deploy.env      # set DOMAIN, ACME_EMAIL, ALLOWED_ORIGINS
```

Deploy:

```bash
./deploy.sh
```

The script reads the database password from SSM into the shell (never to disk),
builds the images, and starts the stack. Caddy requests the certificate on first
start; that takes 10–30 seconds.

---

## Step 8 — Verify it works from outside AWS

Run these **on your laptop**, not the server:

```bash
curl https://api.diegojrobles.com/health
```

Expected:

```json
{"status":"healthy","database":"connected","service":"AI Doctor Chatbot API","database_test":1,"ehr_integration":"enabled","fhir_server":"https://hapi.fhir.org/baseR4"}
```

Confirm the certificate is genuine (no `-k` flag needed — that is the point):

```bash
curl -vI https://api.diegojrobles.com/health 2>&1 | grep -E "SSL certificate|issuer|subject"
```

### Exercising the LLM path end to end

`/advice` requires authentication. Register once, then call it:

```bash
TOKEN=$(curl -s -X POST https://api.diegojrobles.com/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"diego","email":"you@example.com","password":"ChangeMe123!","age":22,"sex":"male","role":"patient"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST https://api.diegojrobles.com/advice \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"symptoms":"mild headache and fatigue","age":30,"sex":"male","duration":"2 days","meds":[],"conditions":[]}'
```

On later runs, log in instead of registering. Note this endpoint takes
**form-encoded** input, not JSON:

```bash
TOKEN=$(curl -s -X POST https://api.diegojrobles.com/auth/login \
  -d 'username=diego&password=ChangeMe123!' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

`/advice` exercises triage and the LLM. It does **not** exercise retrieval —
only `/ehr-advice` calls the vector store. See [Known issues](#known-issues).

---

## Redeploying after a code change

```bash
ssh -i ~/.ssh/aidoctor-key.pem ubuntu@api.diegojrobles.com
cd AI-Doctor-Chatbot-v2
git pull
./deploy.sh
```

Postgres data and the TLS certificate live in Docker volumes and survive this.

Useful checks. Note the `./dc.sh` wrapper rather than plain `docker compose`:
the compose file requires `POSTGRES_PASSWORD`, which `deploy.sh` exports only
into its own process, so a bare `docker compose ps` fails with
`required variable POSTGRES_PASSWORD is missing a value`. The wrapper loads the
same config first, then passes your arguments through.

```bash
./dc.sh ps              # what is running
./dc.sh logs -f api     # follow application logs
./dc.sh logs caddy      # certificate problems show up here
./dc.sh restart api
```

If the wrapper itself is failing, read the containers directly — this needs no
environment at all:

```bash
docker ps                                            # exact container names
docker logs ai-doctor-chatbot-v2-api-1 --tail 40
docker logs ai-doctor-chatbot-v2-caddy-1 --tail 40
```

### Changing a secret

Two machines are involved, on purpose. The instance role is **read-only** on
SSM, so writing a secret from the server fails with:

```
AccessDeniedException ... not authorized to perform: ssm:PutParameter
```

That is the least-privilege design working: a compromised web server can read
the secrets it needs to run, but cannot rewrite them.

**On your laptop** (admin IAM user), write the new value:

```bash
aws ssm put-parameter --name /aidoctor/prod/OPENROUTER_API_KEY \
  --value 'sk-or-v1-NEW' --type SecureString --overwrite
```

**On the server**, restart so the container re-reads SSM. Secrets are loaded at
container start, so a `put-parameter` alone changes nothing:

```bash
./dc.sh restart api
```

Verify the stored key without printing it. A valid OpenRouter key is
`sk-or-v1-` plus 64 hex characters — length 73. Anything longer usually means a
trailing space or newline was captured when copying:

```bash
aws ssm get-parameter --name /aidoctor/prod/OPENROUTER_API_KEY --with-decryption \
  --query Parameter.Value --output text \
  | awk '{print "prefix:", substr($0,1,12) "... length:", length($0)}'
```

Confirm the key is actually accepted by the provider (reads work on the server):

```bash
KEY=$(aws ssm get-parameter --name /aidoctor/prod/OPENROUTER_API_KEY \
  --with-decryption --query Parameter.Value --output text)
curl -s -o /dev/null -w '%{http_code}\n' \
  https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $KEY"
```

`200` means the key is valid. `401` means SSM holds a wrong or revoked key --
`put-parameter` succeeds regardless of whether the value is a working key, so a
stale paste looks identical to success until the app tries to use it.

---

## Teardown

This stops all billing. Run on your laptop, using the IDs from Step 5.

```bash
# 1. Terminate the instance (this also deletes its EBS volume)
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"

# 2. Release the Elastic IP. UNUSED ELASTIC IPS ARE BILLED -- do not skip this.
aws ec2 release-address --allocation-id "$ALLOC_ID"

# 3. Delete the security group
aws ec2 delete-security-group --group-id "$SG_ID"

# 4. Delete the key pair
aws ec2 delete-key-pair --key-name aidoctor-key

# 5. Delete the secrets
for p in OPENROUTER_API_KEY PINECONE_API_KEY PINECONE_INDEX_NAME POSTGRES_PASSWORD SECRET_KEY; do
  aws ssm delete-parameter --name "/aidoctor/prod/$p"
done

# 6. Delete the IAM role and instance profile
aws iam remove-role-from-instance-profile \
  --instance-profile-name aidoctor-instance-profile --role-name aidoctor-instance-role
aws iam delete-instance-profile --instance-profile-name aidoctor-instance-profile
aws iam delete-role-policy --role-name aidoctor-instance-role --policy-name aidoctor-ssm-read
aws iam delete-role --role-name aidoctor-instance-role

# 7. Delete the budgets
ACCT=$(aws sts get-caller-identity --query Account --output text)
aws budgets delete-budget --account-id "$ACCT" --budget-name aidoctor-5-dollar
aws budgets delete-budget --account-id "$ACCT" --budget-name aidoctor-15-dollar
```

Also remove the DNS `A` record, and delete the `deploy-admin` IAM user in the
console if you no longer need it.

Confirm nothing is left running:

```bash
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`].Value|[0]]'
aws ec2 describe-addresses --query 'Addresses[].PublicIp'
```

Both should return empty.

---

## Cost

Verify current prices at <https://calculator.aws> — AWS changes them, and free
tier eligibility depends on your account's age.

| Resource | Approx. monthly |
|---|---|
| EC2 `t4g.micro` on-demand | ~$6.13 |
| EBS gp3, 20 GB | ~$1.60 |
| Elastic IP (public IPv4) | ~$3.60 |
| SSM Parameter Store (standard tier) | $0.00 |
| AWS Budgets (first two are free) | $0.00 |
| Data transfer out (low volume) | ~$0–1 |
| **Total** | **~$11–12** |

If your account is still within its first 12 months you may qualify for free
`t3.micro` hours, which would reduce this further. Check **Billing → Free Tier**
in the console.

Stepping up to `t4g.small` (2 GB RAM) roughly doubles the instance cost to
~$12.26 and pushes the total to about $17 — over budget. Start on `micro` with
the swap file; resizing later is a stop, a change, and a start.

---

## Known issues

Found while testing this deployment locally. None are caused by the deployment
itself, but two of them limit what works in production.

**1. Pinecone index does not exist — retrieval is entirely non-functional.**
On startup the app logs:

```
❌ Pinecone initialization error: [404 NOT_FOUND] Resource medical-knowledge not found
```

Every retrieval returns zero documents. `/ehr-advice` silently degrades to an
LLM-only answer with no citations. Create and populate the index before
retrieval will work:

```bash
python backend/app/scripts/load_medical_data.py
```

**2. `/ehr-advice` returns 502.** The LLM response fails schema validation
against `EnhancedAdviceOutWithReminders` with three missing fields. This is
independent of deployment and reproduces locally. `/advice` is unaffected.

**3. Symptom tracking throws on a fresh database.**

```
psycopg2.errors.InvalidColumnReference: there is no unique or exclusion
constraint matching the ON CONFLICT specification
```

An `ON CONFLICT` clause references a constraint that `Base.metadata.create_all()`
does not create. It is caught and logged rather than surfaced, so requests still
succeed, but monthly symptom aggregates are never written.

**4. `chroma_storage/` is dead weight.** Nothing reads it — retrieval moved to
Pinecone. It is excluded from the image via `.dockerignore`. Consider deleting it.

---

## Troubleshooting

**`curl` hangs or connection refused.** Check DNS resolves (`dig +short
api.diegojrobles.com`) and that ports 80/443 are open in the security group.

**Certificate errors.** `docker compose logs caddy`. Almost always DNS not yet
pointing at the box when Caddy first started. Fix DNS, then `docker compose
restart caddy`. Let's Encrypt rate-limits repeated failures, so do not loop.

**`entrypoint: FATAL - could not read SSM parameters`.** The instance role is
missing or wrong. Confirm with:

```bash
aws sts get-caller-identity          # run ON the instance
aws ssm get-parameters-by-path --path /aidoctor/prod/ --query 'Parameters[].Name'
```

**Container killed / out of memory.** Confirm swap is active with `free -h`.
If it recurs, move up to `t4g.small`.
