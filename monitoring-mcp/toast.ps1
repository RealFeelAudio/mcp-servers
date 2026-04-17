param(
    [string]$Title   = "Claude Monitor",
    [string]$Message = ""
)

try {
    [Windows.UI.Notifications.ToastNotificationManager,
     Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument,
     Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
<toast duration="short">
  <visual>
    <binding template="ToastGeneric">
      <text>$Title</text>
      <text>$Message</text>
    </binding>
  </visual>
</toast>
"@

    $xml = [Windows.Data.Xml.Dom.XmlDocument]::New()
    $xml.LoadXml($template)

    $AppId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
    $toast    = [Windows.UI.Notifications.ToastNotification]::New($xml)
    $notifier.Show($toast)
    Start-Sleep -Seconds 1
}
catch {
    # Fallback: system tray balloon
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Information
        $n.BalloonTipTitle = $Title
        $n.BalloonTipText  = $Message
        $n.Visible = $true
        $n.ShowBalloonTip(5000)
        Start-Sleep -Seconds 2
        $n.Dispose()
    }
    catch {}
}
