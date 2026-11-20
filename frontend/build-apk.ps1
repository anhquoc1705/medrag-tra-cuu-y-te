# Build app Android (file APK để cài lên điện thoại) từ giao diện web – GĐ 10, phần thêm ngoài đề cương.
#
#   powershell -ExecutionPolicy Bypass -File frontend\build-apk.ps1                                   # máy chủ mặc định (VITE_API_URL)
#   powershell -ExecutionPolicy Bypass -File frontend\build-apk.ps1 -ApiUrl https://ten-may-chu.duckdns.org
#
# -ApiUrl: địa chỉ backend ghi sẵn vào app. Không bắt buộc – sau khi cài vẫn đổi được trong app (menu ☰ → "Máy chủ").
# Kết quả: frontend\android\app\build\outputs\apk\debug\app-debug.apk (bản debug: tự ký, cài trực tiếp được).
# Cần: JDK 21 (C:\Program Files\Java\jdk-21.0.10), Android SDK ở D:\Android_Data\sdk (cài cùng Android Studio, đã chuyển từ ổ C).

param([string]$ApiUrl = "")

$ErrorActionPreference = "Stop"
$Frontend = $PSScriptRoot
Set-Location $Frontend

if ($ApiUrl) { $env:VITE_API_URL = $ApiUrl.TrimEnd("/") }
npm run build
if ($LASTEXITCODE -ne 0) { throw "Build giao diện web lỗi" }
npx cap sync android
if ($LASTEXITCODE -ne 0) { throw "cap sync lỗi" }

# JDK 21 (Capacitor 8 yêu cầu). Không dùng D:\Android\jbr: đó là Java 25, Gradle 8.14 chưa hỗ trợ
# ("Unsupported class file major version 69").
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.10"
# 17/11: Android SDK, Gradle, máy ảo đã chuyển sang D:\Android_Data (ổ C đầy); biến môi trường người dùng trỏ tới đó.
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = "D:\Android_Data\sdk" }
if (-not $env:GRADLE_USER_HOME) { $env:GRADLE_USER_HOME = "D:\Android_Data\gradle" }
Set-Location (Join-Path $Frontend "android")
.\gradlew.bat assembleDebug --console=plain
if ($LASTEXITCODE -ne 0) { throw "Gradle build lỗi" }

$apk = Join-Path $Frontend "android\app\build\outputs\apk\debug\app-debug.apk"
Write-Host ("Xong: {0} ({1:N1} MB)" -f $apk, ((Get-Item $apk).Length / 1MB))
