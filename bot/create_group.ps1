param(
    [string]$DataFile    = "/data/data.txt",
    [string]$StorageDir  = "/shared/storage",
    [int]   $GroupsPer   = 10,
    [string]$GroupPrefix = 'new_batch',
    [string]$OutputLog   = "/shared/creation_log.txt"
)

Install-Module ExchangeOnlineManagement -Force -Scope CurrentUser | Out-Null
Import-Module ExchangeOnlineManagement -ErrorAction Stop

"Account,GroupName,SmtpAddress,Action,Status,Message" | Out-File -FilePath $OutputLog -Encoding UTF8

if (-not (Test-Path $DataFile)) { Throw "Data file '$DataFile' not found." }
if (-not (Test-Path $StorageDir)) { Throw "Storage directory '$StorageDir' not found." }

$credLines = Get-Content $DataFile | Where-Object { $_.Trim() -ne '' }

function Login-User {
    param([string]$UPN,[string]$Password)
    $securePass = ConvertTo-SecureString $Password -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($UPN,$securePass)
    try {
        Connect-ExchangeOnline -Credential $cred -ShowBanner:$false -ErrorAction Stop
        return $true
    } catch {
        # use braced variable to avoid parser confusion with colon
        Write-Warning "Login failed for ${UPN}: $($_.Exception.Message)"
        return $false
    }
}

function Create-ModeratedDG {
    param([string]$Name,[string]$Domain,[string]$Moderator)
    try {
        $dg = New-DistributionGroup -Name $Name -RequireSenderAuthenticationEnabled $false -ErrorAction Stop
        $smtp = "${Name}@${Domain}"
        Set-DistributionGroup -Identity $dg.Identity -PrimarySmtpAddress $smtp
        Set-DistributionGroup -Identity $dg.Identity -ModerationEnabled $true -ModeratedBy $Moderator -SendModerationNotifications Always
        return @{ Status='Success'; Smtp=$smtp; Message='' }
    } catch {
        return @{ Status='Failed'; Smtp="${Name}@${Domain}"; Message=$_.Exception.Message }
    }
}

function Add-Members {
    param([string]$SmtpAddress,[string[]]$Members)
    foreach($m in $Members) {
        try {
            Add-DistributionGroupMember -Identity $SmtpAddress -Member $m -ErrorAction Stop
            "$SmtpAddress,AddMember,$m,Success," | Out-File -FilePath $OutputLog -Append
        } catch {
            "$SmtpAddress,AddMember,$m,Failed,'$($_.Exception.Message)'" | Out-File -FilePath $OutputLog -Append
        }
    }
}

[int]$index = 1
foreach ($line in $credLines) {
    $parts    = $line -split '\s+',2
    $upn      = $parts[0].Trim()
    $password = if ($parts.Count -gt 1) { $parts[1].Trim() } else { '' }
    $domain   = $upn.Split('@')[1]

    Write-Host "[$index/$($credLines.Count)] Logging in $upn..."
    if (-not (Login-User -UPN $upn -Password $password)) {
        "$upn,Login,,Failed,Login failed" | Out-File -FilePath $OutputLog -Append
        $index++; continue
    }

    $chunkFile = Join-Path $StorageDir ("${upn}.txt")
    $members   = if (Test-Path $chunkFile) { Get-Content $chunkFile } else { @() }

    for ($i=1; $i -le $GroupsPer; $i++) {
        $grpName = "${GroupPrefix}$i"
        $res     = Create-ModeratedDG -Name $grpName -Domain $domain -Moderator $upn

        if ($res.Status -eq 'Success') {
            Write-Host "  ✔ Created $($res.Smtp)"
            "$upn,$grpName,$($res.Smtp),CreateDG,Success," | Out-File -FilePath $OutputLog -Append
            if ($members.Count -gt 0) { Add-Members -SmtpAddress $res.Smtp -Members $members }
        } else {
            Write-Host "  ✘ $($res.Smtp): $($res.Message)"
            "$upn,$grpName,$($res.Smtp),CreateDG,Failed,'$($res.Message)'" | Out-File -FilePath $OutputLog -Append
        }
    }

    Disconnect-ExchangeOnline -Confirm:$false
    $index++
}

Write-Host "`nAll done. See $OutputLog for details."
