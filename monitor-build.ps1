# Monitor Docker Build Progress
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RASA CHATBOT - DOCKER BUILD MONITOR" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$lastLines = 0
$maxWaitTime = 900  # 15 minutes
$startTime = Get-Date
$checkInterval = 5  # seconds

while ($true) {
    $elapsed = (Get-Date) - $startTime
    if ($elapsed.TotalSeconds -gt $maxWaitTime) {
        Write-Host "Build timeout reached" -ForegroundColor Red
        break
    }
    
    # Get file size and line count
    if (Test-Path build.log) {
        $fileSize = (Get-Item build.log).Length / 1MB
        $currentLines = @(Get-Content build.log 2>/dev/null).Count
        
        if ($currentLines -gt $lastLines) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Build progressing... ($currentLines lines, $([Math]::Round($fileSize, 2)) MB)" -ForegroundColor Yellow
            $lastLines = $currentLines
        }
    }
    
    # Check Docker containers
    $containers = docker ps --format '{{.Names}}: {{.Status}}' 2>/dev/null
    if ($containers) {
        Write-Host ""
        Write-Host "Running Containers:" -ForegroundColor Green
        $containers | ForEach-Object { Write-Host "  ✓ $_" -ForegroundColor Cyan }
        Write-Host ""
    }
    
    # Check for errors in build log
    $errors = Select-String -Path build.log -Pattern "ERROR|error|Failed|failed" -ErrorAction SilentlyContinue | Select-Object -Last 3
    if ($errors) {
        Write-Host "⚠️  Potential issues found:" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host "  - $($_.Line)" -ForegroundColor Red }
    }
    
    Start-Sleep -Seconds $checkInterval
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETE - Checking Final Status" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$finalContainers = docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
if ($finalContainers) {
    Write-Host "Final Container Status:" -ForegroundColor Green
    Write-Host $finalContainers
} else {
    Write-Host "No containers found!" -ForegroundColor Red
}
