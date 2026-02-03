# Add Clawd Fiverr screening cron on a sparky (run after moltbot onboard --install-daemon and channel setup).
# Usage:
#   .\scripts\clawd\add_fiverr_cron.ps1 -TelegramChatId "-1001234567890"
#   .\scripts\clawd\add_fiverr_cron.ps1 -Host sparky1 -TelegramChatId "YOUR_CHAT_ID"
#   .\scripts\clawd\add_fiverr_cron.ps1   # prints the command to run manually with your chat ID
param(
    [string]$HostName = "sparky1",
    [string]$TelegramChatId = "",
    [switch]$NoDelivery = $false,
    [string]$Schedule = "0 */6 * * *",
    [string]$Tz = "America/Los_Angeles"
)

$message = "Use web search or web fetch to find current Fiverr gigs (e.g. writing, logo design, data entry). Summarize up to 10: title, price, link. Report in a short bullet list. Do not log in; use only public pages."

if (-not $TelegramChatId -and -not $NoDelivery) {
    Write-Host "No -TelegramChatId. Run this on the host where Clawd gateway runs (e.g. sparky1):" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  ssh $HostName" -ForegroundColor Gray
    Write-Host "  source ~/.bashrc  # or open new shell" -ForegroundColor Gray
    Write-Host "  moltbot cron add --name 'Fiverr screen' --cron '$Schedule' --tz '$Tz' \"
    Write-Host "    --session isolated --message `"$message`" \"
    Write-Host "    --deliver --channel telegram --to YOUR_CHAT_ID"
    Write-Host ""
    Write-Host "Or: -NoDelivery to add cron without channel; or -TelegramChatId YOUR_CHAT_ID" -ForegroundColor Yellow
    exit 0
}

# Escape single quotes in message for remote bash: ' -> '\''
$msgEscaped = $message -replace "'", "'\''"
$deliverPart = if ($NoDelivery) { "" } else { " --deliver --channel telegram --to '$TelegramChatId'" }
$remoteCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; clawdbot cron add --name 'Fiverr screen' --cron '$Schedule' --tz '$Tz' --session isolated --message '$msgEscaped'$deliverPart"
Write-Host "Adding Fiverr screen cron on $HostName$(if ($NoDelivery) { ' (no delivery)' } else { " (deliver to Telegram $TelegramChatId)" })..." -ForegroundColor Cyan
try {
    ssh $HostName $remoteCmd
    Write-Host "Done. List jobs: ssh $HostName 'clawdbot cron list'" -ForegroundColor Green
} catch {
    Write-Host "Failed: $_" -ForegroundColor Red
    Write-Host "Run the command manually on $HostName (see docs/external-tools/clawd/CLAWD_SPARKY.md)." -ForegroundColor Yellow
    exit 1
}
