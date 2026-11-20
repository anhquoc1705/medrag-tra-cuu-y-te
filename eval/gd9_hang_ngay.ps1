# GĐ 9 – chạy đánh giá hằng ngày đến khi hết hạn mức miễn phí (SV duyệt 14/11/2026).
#
# Chạy lần lượt (máy chủ 12 GB không đủ 3 tiến trình nạp bge-m3 cùng lúc; hạn mức tính riêng từng nhà cung cấp
# nên chạy lần lượt vẫn dùng hết hạn mức trong ngày):
#   1. (bỏ 15/11) Gemini 3.8 Flash – 20 lượt/ngày, quá tải liên tục
#   2. Gemini 3.5 Flash-Lite : llm_only + hybrid_rag_guard          (~500 lượt/ngày, file riêng – SV chọn 14/11)
#   3. Llama 3  : llm_only + hybrid_rag_guard   (Cloudflare)         (10.000 neuron/ngày)
#   4. Qwen     : llm_only + vector_rag + hybrid_rag + hybrid_rag_guard (Groq, 200.000 token/ngày)
# Bộ câu hỏi: 50/100 câu test (eval/test50_ids.txt). Mỗi phần dùng --resume: chạy tiếp câu chưa làm / câu lỗi,
# hết hạn mức ngày thì guard_eval.py tự dừng (mã 2) → chuyển sang phần sau. Xong hết thì các lần sau chỉ in tổng hợp.
#
# Chạy tay:  powershell -ExecutionPolicy Bypass -File eval\gd9_hang_ngay.ps1
# Tự chạy :  Task Scheduler, tác vụ "MedRAG GD9" lúc 7:15 hằng ngày (Cloudflare reset neuron lúc 7:00 giờ VN).
# Nhật ký :  eval\results\gd9_log_<ngày>.txt (tóm tắt) + gd9_log_<ngày>_<phần>.txt (chi tiết)  (eval/results không lên GitHub)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # đọc đúng tiếng Việt từ python
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Log = Join-Path $Root ("eval\results\gd9_log_{0:yyyyMMdd}.txt" -f (Get-Date))

function Write-Log($msg) {
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $msg
    Add-Content -Path $Log -Value $line -Encoding utf8
}

Write-Log "=== Bắt đầu GĐ 9 hằng ngày ==="

# 1. Docker Desktop + 3 kho dữ liệu (Elasticsearch, Milvus, PostgreSQL)
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) { Write-Log "Docker chưa chạy – mở Docker Desktop"; Start-Process $dd }
    for ($i = 0; $i -lt 60; $i++) {          # chờ tối đa 10 phút
        Start-Sleep -Seconds 10
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
    }
}
docker start medrag-postgres medrag-es medrag-milvus 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $Log -Encoding utf8
$ready = $false
for ($i = 0; $i -lt 60; $i++) {              # chờ ES + Milvus báo healthy, tối đa 10 phút
    $es = docker inspect -f "{{.State.Health.Status}}" medrag-es 2>$null
    $mv = docker inspect -f "{{.State.Health.Status}}" medrag-milvus 2>$null
    if ($es -eq "healthy" -and $mv -eq "healthy") { $ready = $true; break }
    Start-Sleep -Seconds 10
}
if (-not $ready) { Write-Log "DỪNG: Elasticsearch/Milvus chưa sẵn sàng sau 10 phút"; exit 1 }
Write-Log "Kho dữ liệu sẵn sàng"

# 2. Chạy lần lượt từng nhà cung cấp
# 14/11 (SV chọn): đánh giá CẢ HAI mô hình Gemini, mỗi mô hình một file – chạy 3.8 Flash trước (20 lượt/ngày,
# hay quá tải 503), hết hạn mức thì sang 3.5 Flash-Lite (~500 lượt/ngày). Không gộp kết quả 2 mô hình.
# 15/11 (SV chọn): BỎ Gemini 3.8 Flash – 20 lượt/ngày + quá tải 503/504 liên tục, không kịp hạn. Gemini chỉ còn 3.5 Flash-Lite.
$runs = @(
    # @{ name = "Gemini 3.8 Flash";    provider = "gemini"; model = "gemini-3.8-flash";      out = "gd9_test50_gemini.jsonl";        configs = @("llm_only", "hybrid_rag_guard") },
    @{ name = "Gemini 3.5 Flash-Lite"; provider = "gemini"; model = "gemini-3.5-flash-lite"; out = "gd9_test50_gemini35lite.jsonl"; configs = @("llm_only", "hybrid_rag_guard") },
    @{ name = "Llama 3"; provider = "cloudflare"; model = ""; out = "gd9_test50_llama.jsonl";  configs = @("llm_only", "hybrid_rag_guard") },
    @{ name = "Qwen";    provider = "groq";       model = ""; out = "gd9_test50_qwen.jsonl";   configs = @("llm_only", "vector_rag", "hybrid_rag", "hybrid_rag_guard") }
)
foreach ($r in $runs) {
    Write-Log ("--- {0}: {1}" -f $r.name, ($r.configs -join ", "))
    # 14/11: lượt hôm trước có thể còn chạy (Groq hết token → ngủ chờ qua đêm) → 2 tiến trình ghi cùng 1 file sẽ hỏng kết quả
    $busy = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -match "guard_eval\.py" -and $_.CommandLine -match [regex]::Escape($r.out) }
    if ($busy) { Write-Log ("{0}: bỏ qua – lượt trước vẫn đang chạy (PID {1})" -f $r.name, ($busy.ProcessId -join ", ")); continue }
    $pyArgs = @("eval\guard_eval.py", "--provider", $r.provider, "--configs") + $r.configs +
              @("--ids-file", "eval\test50_ids.txt", "--out", $r.out, "--resume")
    if ($r.model) { $pyArgs += @("--model", $r.model) }
    # Nhật ký riêng từng phần, ghi qua cmd ">>" (không khoá file – mở xem được khi đang chạy; 14/11 Add-Content khoá file)
    $runLog = $Log -replace "\.txt$", ("_{0}.txt" -f ($r.out -replace "^gd9_test50_|\.jsonl$", ""))
    Write-Log "    nhật ký: $runLog"
    # Không dùng ngoặc kép bên trong (PS 5.1 làm hỏng ngoặc kép khi truyền sang cmd) – đường dẫn dự án không có dấu cách
    $cmdLine = "{0} {1} >> {2} 2>&1" -f $Python, ($pyArgs -join " "), $runLog
    cmd /d /c $cmdLine
    $code = $LASTEXITCODE
    $note = switch ($code) { 0 { "xong phần này (hoặc đã xong từ trước)" } 2 { "hết hạn mức ngày – mai chạy tiếp" } default { "lỗi (mã $code)" } }
    Write-Log ("{0}: {1}" -f $r.name, $note)
}
Write-Log "=== Kết thúc ==="
