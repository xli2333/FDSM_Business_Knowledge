# Reset to unstage everything (in case sensitive files were staged)
git reset

# Add everything (respecting the new .gitignore)
git add .

# Commit
git commit -m "Deployment Ready: Core code, DB, and Index (Raw data excluded)"

# Add Remote (Force update if exists)
if (git remote | Select-String "origin") {
    git remote set-url origin https://github.com/xli2333/FDSMNEWSCOLLECTION
} else {
    git remote add origin https://github.com/xli2333/FDSMNEWSCOLLECTION
}

# Instruction for User
Write-Host "✅ Git repository initialized and changes committed."
Write-Host "🚀 NOW RUN THE FOLLOWING COMMAND TO PUSH (Use your proxy if needed):"
Write-Host '$env:HTTP_PROXY="http://127.0.0.1:10080"; $env:HTTPS_PROXY="http://127.0.0.1:10080"; git push -f origin main'
