# Railway Deployment Guide

This application is ready to deploy on Railway.

## Repository Structure

The git repository root is `pepsi-options-emails/` which contains:
- All Python modules (`db.py`, `email_service.py`, `main.py`, `scheduler.py`)
- `run_server.py` - Server startup script
- `requirements.txt` - Python dependencies
- `Procfile` - Railway start command
- `runtime.txt` - Python version

## Quick Deploy

1. **Connect your repository to Railway**
   - Go to [Railway](https://railway.app)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select the `pepsi-options-emails` repository

2. **Set Environment Variables in Railway**
   
   Go to your Railway project → Variables tab and add:

   **Required:**
   ```
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_REGION=us-east-2
   LAMBDA_FUNCTION_NAME=your-function-name
   EMAIL_TO=recipient@example.com
   SENDER_EMAIL=sender@example.com
   ORG_ID=01970f4c-c79d-7858-8034-60a265d687e4
   SUPABASE_URL=your-supabase-url
   SUPABASE_KEY=your-supabase-key
   ```

   **Optional:**
   ```
   PORT=8000                    # Default: 8000 (Railway sets this automatically)
   ENABLE_EMAIL_SCHEDULER=false # Set to "true" to enable scheduled emails
   EMAIL_SCHEDULE_INTERVAL_MINUTES=60
   EMAIL_COOLDOWN_MINUTES=60
   DATA_DIR=/tmp                # Directory for cooldown file
   ```

   **For multiple recipients:**
   ```
   EMAIL_TO="email1@example.com, email2@example.com, email3@example.com"
   ```

3. **Deploy**
   - Railway will automatically detect the `Procfile` and deploy
   - The app will start on the port Railway assigns (check Railway dashboard)

## How Railway Detects the App

Railway uses the `Procfile` which contains:
```
web: python run_server.py
```

This tells Railway to:
- Run `python run_server.py` as the web process
- Use the `PORT` environment variable (Railway sets this automatically)
- The app listens on `0.0.0.0` to accept external connections

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | Yes | - | AWS access key for Lambda invocation |
| `AWS_SECRET_ACCESS_KEY` | Yes | - | AWS secret key |
| `AWS_REGION` | Yes | - | AWS region (e.g., us-east-2) |
| `LAMBDA_FUNCTION_NAME` | Yes | - | Name of Lambda function to invoke |
| `EMAIL_TO` | Yes | - | Recipient email(s), comma-separated for multiple |
| `SENDER_EMAIL` | Yes | - | Sender email address |
| `ORG_ID` | Yes | - | Organization ID for database queries |
| `SUPABASE_URL` | Yes | - | Supabase project URL |
| `SUPABASE_KEY` | Yes | - | Supabase API key |
| `PORT` | No | 8000 | Port (Railway sets this automatically) |
| `ENABLE_EMAIL_SCHEDULER` | No | false | Enable scheduled emails |
| `EMAIL_SCHEDULE_INTERVAL_MINUTES` | No | 60 | Interval for scheduled emails |
| `EMAIL_COOLDOWN_MINUTES` | No | 60 | Cooldown period between emails |
| `DATA_DIR` | No | /tmp | Directory for storing cooldown file |

## Testing After Deployment

Once deployed, Railway will provide a URL like: `https://your-app.railway.app`

You can test the endpoints:

```bash
# Check scheduler status
curl https://your-app.railway.app/scheduler/status

# Send email
curl -X POST https://your-app.railway.app/send-email \
  -H "Content-Type: application/json" \
  -d '{"org_id": "01970f4c-c79d-7858-8034-60a265d687e4"}'

# View API docs
# Visit: https://your-app.railway.app/docs
```

## Important Notes

1. **Port**: Railway automatically sets the `PORT` environment variable. The app reads this automatically.

2. **Cooldown File**: The cooldown file is stored in `/tmp` by default. On Railway, this is ephemeral storage that resets on each deploy. If you need persistence, consider using Railway's volume feature or a database.

3. **Scheduler**: If you enable the scheduler, it will run in the same process as the web server. For production, consider using Railway's cron jobs or external schedulers for more reliability.

4. **Health Checks**: Railway will check if the app is responding on the assigned port. The app starts listening immediately, so this should work automatically.

## Troubleshooting

**App won't start:**
- Check Railway logs for errors
- Verify all required environment variables are set
- Ensure `requirements.txt` is present and correct

**Lambda invocation fails:**
- Verify AWS credentials are correct
- Check Lambda function name matches exactly
- Verify AWS region is correct

**Database queries fail:**
- Verify Supabase URL and key are correct
- Check network connectivity (Railway should have outbound access)

**Emails not sending:**
- Check Lambda function logs in AWS Console
- Verify EMAIL_TO and SENDER_EMAIL are set correctly
- Check cooldown status: `GET /scheduler/status`

