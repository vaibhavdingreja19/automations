# Get working directory safely (replace with hardcoded path if needed)
$workingDir = Get-Location
Write-Host "📂 Working Directory: $workingDir"

# Step 1: Take ownership (handles .git and permission issues)
Write-Host "🔐 Taking ownership..."
takeown /f "$workingDir" /r /d y | Out-Null
icacls "$workingDir" /grant "*S-1-5-32-544:F" /t /c /q | Out-Null

# Step 2: Remove read-only, system, hidden attributes
Write-Host "🧹 Clearing attributes from all items..."
Get-ChildItem -Path $workingDir -Recurse -Force | ForEach-Object {
    try {
        attrib -Hidden -System -ReadOnly $_.FullName
    } catch {
        Write-Warning "⚠️ Failed to remove attributes: $($_.FullName)"
    }
}

# Step 3: Delete only the contents (not the folder itself)
Write-Host "🗑️ Deleting contents inside working directory..."
try {
    Get-ChildItem -Path $workingDir -Force | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "✅ Contents deleted successfully!"
} catch {
    Write-Error "❌ Error deleting contents:"
    Write-Error $_.Exception.Message
}
