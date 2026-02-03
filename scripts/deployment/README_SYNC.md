# Git Sync Workflow for Multi-Machine Development

## Overview

This project uses a **shared git repository** (`ai2ai`) across three machines:
- **Local machine** (Windows): Main development machine with GitHub authentication
- **sparky1** (Linux): Deployment server 1
- **sparky2** (Linux): Deployment server 2

## Recommended Workflow

### Option 1: Sync Script (Recommended)

Use the PowerShell sync script to push/pull changes:

```powershell
# Push your changes to GitHub and sync to sparkies
.\scripts\deployment\sync_to_sparkies.ps1 push

# Pull latest from GitHub and sync to sparkies
.\scripts\deployment\sync_to_sparkies.ps1 pull

# Do both (default)
.\scripts\deployment\sync_to_sparkies.ps1 both
```

**How it works:**
1. On local machine: commits/pushes to GitHub (you have auth)
2. Syncs files directly to sparky1/sparky2 via scp
3. Sparkies can use git locally for tracking, but don't need GitHub auth

### Option 2: Manual Git on Sparkies

If you set up GitHub authentication on sparky1/sparky2 (SSH keys or tokens):

```bash
# On sparky1 or sparky2
cd ~/ai_ai2ai
git pull origin main
# Make changes...
git add -A
git commit -m "Your changes"
git push origin main
```

### Option 3: Local Machine as Hub

Always work on local machine, then sync:
1. Make changes locally
2. Commit and push to GitHub
3. Run sync script to deploy to sparkies
4. Sparkies pull from GitHub when needed

## Setup

### Initial Setup on Sparkies

Run once on each sparky machine:

```bash
cd ~/ai_ai2ai
bash ~/ai_ai2ai/scripts/git/setup_git_sparkies.sh
```

This will:
- Initialize git (if not already done)
- Add remote pointing to GitHub
- Set up branch tracking

### SSH Key Setup (Optional but Recommended)

To enable direct git pull/push on sparky1 and sparky2:

**Step 1: Add SSH keys to GitHub**

1. Create a GitHub Personal Access Token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scope: `admin:public_key`
   - Copy the token

2. Run the setup script:
   ```powershell
   $env:GITHUB_TOKEN = "your_token_here"
   .\scripts\git\add_ssh_keys_to_github.ps1
   ```

**Step 2: Update git remotes to use SSH**

```powershell
.\scripts\git\update_git_remotes_to_ssh.ps1
```

After this, sparky1 and sparky2 can use `git pull` and `git push` directly!

### Daily Workflow

**On local machine:**
```powershell
# 1. Make your changes
# 2. Commit
git add -A
git commit -m "Your changes"

# 3. Push and sync
.\scripts\deployment\sync_to_sparkies.ps1 push
```

**On sparky1/sparky2 (if you have GitHub auth):**
```bash
cd ~/ai_ai2ai
git pull origin main
# Or if you made local changes:
git add -A
git commit -m "Local changes"
git push origin main
```

## File Organization

- **Shared code**: All agents, backend code is shared
- **Deployment-specific**: 
  - `deployment/docker-compose.sparky1.yml` (sparky1 config)
  - `deployment/docker-compose.sparky2.yml` (sparky2 config)
- **Data**: `backend_data/` is not synced (machine-specific)

## Benefits of This Approach

✅ Single source of truth (GitHub repo)  
✅ All machines stay in sync  
✅ Easy to track changes  
✅ Can work from any machine  
✅ Deployment files separated by machine  

## Troubleshooting

**"Could not read Username" error on sparkies:**
- This is normal - sparkies don't have GitHub auth
- Use the sync script from local machine instead

**Conflicts when syncing:**
- Commit your changes locally first
- Pull from GitHub
- Resolve conflicts
- Then sync to sparkies

**Files out of sync:**
- Run `.\scripts\deployment\sync_to_sparkies.ps1 push` to sync everything
- Or manually scp specific files
