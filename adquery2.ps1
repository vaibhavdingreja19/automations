function Get-ADInfoFromJHinfatools {
    param(
        [string]$Username,
        [string]$Domain = "MFCGD"
    )

    $url = "https://jhinfatools.jhancock.com/activedirectory/ActiveDirectory.cgi?domain=$Domain&type=User&pattern=$Username&rm=findUsersOrGroups"

    $response = Invoke-WebRequest $url -UseDefaultCredentials

    $lines = $response.Content -split "`n"

    $target = $lines | Where-Object { $_ -match "\\$Username" -and $_ -match "@" }

    if (-not $target) { return $null }

    # Strip HTML tags
    $plain = ($target -replace "<[^>]+>", " ").Trim()

    # Normalize spacing
    $plain = ($plain -replace "\s+", " ")

    # Extract email (best approach)
    $emailMatch = [regex]::Match($plain, "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    $email = $emailMatch.Value

    # Break into tokens
    $parts = $plain.Split(" ")

    # First element is domain\username
    $domainUser = $parts[0]
    $domain, $user = $domainUser.Split("\\")

    # Extract name tokens (everything before email and before slash paths)
    $nameTokens = @()
    foreach ($p in $parts[1..($parts.Count-1)]) {
        if ($p -eq $email -or $p.StartsWith("/") -or $p.StartsWith("CN=")) { break }
        $nameTokens += $p
    }

    $displayName = $nameTokens -join " "

    # Split into first/last names
    $firstName = $nameTokens[0]
    $lastName = if ($nameTokens.Count -gt 1) { $nameTokens[1..($nameTokens.Count-1)] -join " " } else { "" }

    return [PSCustomObject]@{
        Username     = $user
        Domain       = $domain
        DisplayName  = $displayName
        FirstName    = $firstName
        LastName     = $lastName
        Email        = $email
    }
}

# TEST
Get-ADInfoFromJHinfatools -Username "dingrva"
