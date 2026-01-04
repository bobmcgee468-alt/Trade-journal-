#!/bin/bash
# Deploy Trade Journal Bot to DigitalOcean
# Run this script from your local machine: ./deploy.sh

DROPLET_IP="167.71.99.109"
REMOTE_DIR="/root/trade-journal-bot"

echo "Deploying Trade Journal Bot to DigitalOcean..."

# Step 1: Create directory on server
ssh root@$DROPLET_IP "mkdir -p $REMOTE_DIR"

# Step 2: Copy files to server
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' --exclude 'trades.db' \
    ./ root@$DROPLET_IP:$REMOTE_DIR/

# Step 3: Create .env with ENVIRONMENT=digitalocean
ssh root@$DROPLET_IP "cat > $REMOTE_DIR/.env << 'EOF'
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=8092067485:AAFr8nk5_3TLi7w_6vowNJdj1G0gHB0M7hg

# Restrict bot to only your user ID
ALLOWED_USER_ID=1644767408

# Anthropic API Key (for Claude-powered message parsing)
ANTHROPIC_API_KEY=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

# Environment indicator
ENVIRONMENT=digitalocean
EOF"

# Step 4: Install dependencies
ssh root@$DROPLET_IP "cd $REMOTE_DIR && pip3 install python-telegram-bot python-dotenv requests anthropic"

# Step 5: Kill any existing bot process
ssh root@$DROPLET_IP "pkill -f 'python3.*bot.py' || true"

# Step 6: Start the bot with nohup
ssh root@$DROPLET_IP "cd $REMOTE_DIR && nohup python3 bot.py > bot.log 2>&1 &"

echo ""
echo "Deployment complete!"
echo "Check status: ssh root@$DROPLET_IP 'ps aux | grep bot.py'"
echo "View logs: ssh root@$DROPLET_IP 'tail -f $REMOTE_DIR/bot.log'"
