# Deploy to Vercel - Step by Step Guide

## Prerequisites
- GitHub account with your code repository
- Vercel account (free) at vercel.com

## Step-by-Step Deployment

### 1. Sign Up for Vercel
- Go to [vercel.com](https://vercel.com)
- Click "Start Deploying"
- Sign up with GitHub (recommended for easy integration)

### 2. Import Your Project
- Click "Import Project" or "New Project" 
- Select "Import Git Repository"
- Choose your AlaeAutomates2.0 repository from GitHub
- Click "Import"

### 3. Configure Project Settings
Vercel will auto-detect it's a Python Flask app. If needed, configure:
- **Framework Preset**: Other (it will auto-detect Flask)
- **Root Directory**: Leave as default (/)
- **Build Command**: Leave empty (Vercel handles this)
- **Output Directory**: Leave empty

### 4. Add Environment Variables
In the project settings, add these environment variables:

```
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
ADMIN_TOKEN=your-admin-token-here
```

To generate secure keys:
```bash
# For SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# For ADMIN_TOKEN  
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Deploy
- Click "Deploy"
- Wait 2-3 minutes for deployment to complete
- You'll get a live URL like: `https://your-project-name.vercel.app`

### 6. Test Your Deployment
- Visit your Vercel URL
- Test the monthly statements processor with a small PDF
- All functionality should work exactly as it did locally

## Benefits of Vercel Deployment

✅ **100% Free Forever** - Generous free tier that covers most usage
✅ **Global CDN** - Faster than local development 
✅ **Auto SSL** - HTTPS enabled automatically
✅ **Zero Config** - No Docker, no complex setup
✅ **50MB File Support** - Larger than most free hosting
✅ **Auto Deployments** - Updates automatically when you push to GitHub

## Vercel vs Other Platforms

| Feature | Vercel | Render | Railway | Heroku |
|---------|--------|--------|---------|---------|
| **Free Tier** | ✅ Forever | ❌ Limited | ❌ $5/month | ❌ No longer free |
| **File Size** | 50MB | 25MB | 50MB | 50MB |
| **Memory** | 1GB | 512MB | 1GB | 512MB |
| **Deploy Speed** | 1-2 min | 5-10 min | 3-5 min | 3-5 min |
| **Global CDN** | ✅ Yes | ❌ No | ❌ No | ❌ No |

## Troubleshooting

**Problem**: Build fails
- Solution: Check that `vercel.json` is in your root directory

**Problem**: App doesn't start
- Solution: Ensure environment variables are set correctly

**Problem**: File uploads fail
- Solution: Check file size limits (50MB max)

## Updating Your App
1. Push changes to your GitHub repository
2. Vercel automatically detects changes and redeploys
3. New version is live in 1-2 minutes

That's it! Your app is now running on Vercel's global infrastructure for free.