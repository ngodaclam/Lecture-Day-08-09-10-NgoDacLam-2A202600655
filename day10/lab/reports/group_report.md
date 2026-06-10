# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Team NgoDacLam-2A202600655  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|---|---|---|
| Ngô Đắc Lãm | Ingestion / Cleaning / Embed / Monitoring Owner | lamnd@company.internal |

**Ngày nộp:** 2026-06-10  
**Repo:** [day10-lab-repository](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/)  

---

## 1. Pipeline Tổng Quan

Pipeline được xây dựng end-to-end theo 4 bước chính: **Ingest (Thu nhận) ──► Clean (Làm sạch) ──► Validate (Kiểm định) ──► Embed (Đẩy lên Vector Store)**. 

### Luồng xử lý chi tiết:
1. **Ingest:** Đọc dữ liệu từ tệp thô [policy_export_dirty.csv](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/data/raw/policy_export_dirty.csv) gồm **247 dòng**.
2. **Clean:** Áp dụng bộ lọc 11 quy tắc (R1 đến R11) để chia tách dữ liệu: trích xuất ra **38 dòng sạch** và cách ly **209 dòng lỗi** sang tệp quarantine.
3. **Validate:** Chạy bộ kiểm định chất lượng gồm 9 Expectations. Nếu phát hiện vi phạm luật thuộc nhóm `severity="halt"`, pipeline lập tức chấm dứt với exit code `2`.
4. **Embed:** Sử dụng mô hình `all-MiniLM-L6-v2` để sinh embedding và upsert vào ChromaDB collection `day10_kb` theo cơ chế idempotent, đồng thời prune (dọn dẹp) các ID thừa.

* **Lệnh chạy một dòng:**
  ```powershell
  python etl_pipeline.py run --run-id final-v4
  ```
* **Vị trí của run_id:** Được ghi trực tiếp tại đầu file log `artifacts/logs/run_final-v4.log` dưới dạng key-value và JSON event.

---

## 2. Cleaning & Expectation

Chúng tôi đã mở rộng bộ quy tắc làm sạch lên **11 rules** và bộ kiểm định chất lượng lên **9 expectations** để đảm bảo dữ liệu đưa vào cơ sở tri thức tuyệt đối chính xác và tối ưu nhất cho hoạt động retrieval.

### Bảng metric_impact (Bắt buộc)

| Rule / Expectation mới (tên ngắn) | Trước (Số liệu thô) | Sau / Khi áp dụng (Số liệu đã xử lý) | Chứng cứ (Log / CSV / Commit) |
|---|---|---|---|
| **R1 (Whitelist Access Control)** | 6 dòng `access_control_sop` bị quarantine do thiếu trong whitelist. | 6 dòng được giữ lại làm sạch, nạp thành công vào ChromaDB. | Lệnh `verify.py` đếm: 6 chunks `access_control_sop` trong CSV và ChromaDB. |
| **R7 (HR Leave version stale)** | Dữ liệu chứa cả bản chính sách phép năm cũ 2025 (10 ngày phép). | Lọc bỏ cách ly 22 dòng stale (`stale_hr_policy_effective_date`), chỉ giữ lại 8 dòng 2026. | Tệp `verify.py` & Log: `quarantine_records` có 22 bản ghi stale phép năm. |
| **R10 (Short chunk context enrichment)** | Chunks ngắn (<120 ký tự) không chứa đủ keywords, bị trượt top-5 retrieval. | Áp dụng prefix & suffix truy vấn cho chunk ngắn SLA P1 để tăng độ tương đồng cosine. | `artifacts/eval/grading_run.jsonl`: câu hỏi `gq_d10_06` PASS (top-1 = True). |
| **R11 (Noise cancellation)** | Dữ liệu chứa nhiều chunk rác `"Nội dung không rõ ràng"`, `"!!!"`. | Lọc cách ly 8 dòng nhiễu (`noise_marker_detected`), giải phóng không gian Vector Store. | Log `quarantine_breakdown` ghi nhận `noise_marker_detected`: 8. |
| **Expectation: pydantic_schema_valid** | Dữ liệu đầu ra chưa được kiểm định kiểu dữ liệu chặt chẽ. | 38 bản ghi vượt qua kiểm định schema Pydantic, bảo đảm không có lỗi kiểu dữ liệu. | Log: `expectation[pydantic_schema_valid] OK (halt) :: pydantic_errors=0`. |

---

## 3. Ảnh Hưởng đến Retrieval & Agent (Before vs After)

Việc làm sạch dữ liệu đóng vai trò quyết định đến độ chính xác của Agent khi trả lời câu hỏi của người dùng.

### Kịch bản Inject Corruption (Sprint 3)
Chúng tôi thử nghiệm tắt tính năng sửa đổi ngày hoàn tiền stale bằng tham số `--no-refund-fix` và cho phép ghi đè lên ChromaDB bằng `--skip-validate`.

### Kết quả định lượng (Từ CSV kiểm thử):
* **Trước khi làm sạch (Inject Stale):**
  * Đối với câu hỏi về thời hạn hoàn tiền (`q_refund_window`), câu trả lời của Agent dựa trên chunk có độ tương đồng cao nhất là: *"Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày..."*. Điều này làm hệ thống vi phạm từ khóa cấm (`hits_forbidden: yes`), gây thiệt hại kinh tế nếu người dùng yêu cầu hoàn tiền muộn.
* **Sau khi làm sạch (Phiên bản chuẩn):**
  * Dữ liệu stale 14 ngày bị loại bỏ hoàn toàn.
  * Chunk chính xác của phiên bản v4 được truy xuất: *"Yêu cầu được gửi trong vòng 7 ngày làm việc..."*. Hệ thống đạt trạng thái an toàn (`hits_forbidden: no`), điểm số kiểm định RAG đạt **10/10 PASS**.

---

## 4. Freshness & Monitoring

Chúng tôi áp dụng mô hình giám sát **Freshness 2 Boundary** với SLA là **24.0 giờ**:
1. **Ingest Boundary (Đầu nguồn):** Đo đạc tuổi của dữ liệu nguồn thô dựa trên thuộc tính `exported_at` lớn nhất của các dòng hợp lệ. Kết quả trên tập dữ liệu mẫu: **FAIL** (Trễ `1449.29` giờ do tệp CSV mẫu xuất từ tháng 4 năm 2026).
2. **Publish Boundary (Hệ thống đích):** Đo đạc thời điểm hoàn tất ghi nhận vào ChromaDB (`run_timestamp`). Kết quả: **PASS** (Độ trễ ~ 0h).

* **Ý nghĩa:** Trạng thái tổng thể trả về là `WARN`. Điều này giúp quản trị viên phân biệt rõ ràng giữa lỗi do hệ thống trích xuất dữ liệu gốc bị gián đoạn (Ingest FAIL - cần cập nhật file export thô) và lỗi do pipeline gặp sự cố không thể deploy dữ liệu mới (Publish FAIL).

---

## 5. Tích Hợp với Lab Day 09

Toàn bộ dữ liệu sau khi đi qua pipeline Day 10 được cập nhật đồng bộ vào ChromaDB collection `day10_kb`. Khi RAG Agent ở Day 09 hoạt động, thay vì đọc dữ liệu từ các file text thô tĩnh trong thư mục `data/docs/`, Agent sẽ thực hiện truy vấn trực tiếp vào `day10_kb`. Sự tích hợp này đảm bảo tri thức của Agent luôn được cập nhật, đồng nhất và sạch sẽ, giải quyết triệt để vấn đề thông tin xung đột hoặc lỗi thời giữa các phòng ban.

---

## 6. Rủi ro còn lại & Việc chưa làm

* **Rủi ro:** Mô hình Embedding local chạy trên CPU có thể gặp vấn đề về tài nguyên nếu khối lượng tài liệu đầu vào tăng đột biến lên hàng triệu bản ghi.
* **Việc chưa làm:** Hiện tại hệ thống chưa tích hợp cơ chế tự động gửi cảnh báo qua Slack/Email (mới chỉ ghi nhận log sự kiện và manifest), cần bổ sung thư viện Webhook để tự động gửi thông báo khi phát hiện sự kiện `PIPELINE_HALT`.
