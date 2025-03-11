Invoke-WebRequest -Uri https://aka.ms/installazurecliwindows -OutFile .\AzureCLI.msi; Start-Process msiexec.exe -ArgumentList "/I AzureCLI.msi /quiet" -Wait; Remove-Item .\AzureCLI.msi
