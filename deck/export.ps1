# Експорт презентації в PDF (і PNG для перевірки) через встановлений PowerPoint.
# Запуск:  powershell -ExecutionPolicy Bypass -File deck/export.ps1 [-Png <тека>]
param(
    [string]$Pptx = "presentation/NBU_University_Challenge_2026.pptx",
    [string]$Png = ""
)
$ErrorActionPreference = "Stop"
$pptxPath = (Resolve-Path $Pptx).Path
$pdfPath = [System.IO.Path]::ChangeExtension($pptxPath, ".pdf")
$app = New-Object -ComObject PowerPoint.Application
try {
    # ReadOnly, Untitled, WithWindow = false
    $pres = $app.Presentations.Open($pptxPath, -1, 0, 0)
    $pres.SaveAs($pdfPath, 32)          # ppSaveAsPDF
    Write-Output "PDF: $pdfPath"
    if ($Png -ne "") {
        New-Item -ItemType Directory -Force $Png | Out-Null
        $pngPath = (Resolve-Path $Png).Path
        for ($i = 1; $i -le $pres.Slides.Count; $i++) {
            $file = Join-Path $pngPath ("slide-{0:D2}.png" -f $i)
            $pres.Slides.Item($i).Export($file, "PNG", 1600, 900)
        }
        Write-Output "PNG: $pngPath"
    }
    $pres.Close()
}
finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
