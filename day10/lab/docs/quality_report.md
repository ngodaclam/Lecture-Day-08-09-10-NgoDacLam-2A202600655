# Quality Report — Lab Day 10

**run_id:** demo-thuc-te  
**Ngày:** 2026-06-10

Báo cáo chi tiết chất lượng dữ liệu và kiểm định retrieval trước và sau khi tối ưu hóa bộ lọc làm sạch dữ liệu (Data Cleaning & Quality Rules).

---

## 1. Tóm tắt số liệu chất lượng

Dưới đây là so sánh số lượng bản ghi thô, bản ghi đạt chuẩn làm sạch, và bản ghi bị cách ly lỗi giữa phiên chạy bị lỗi (Inject Bad Data) và phiên chạy làm sạch thực tế (`demo-thuc-te`):

| Chỉ số | Trước (Inject Bad / Stale Data) | Sau (Làm sạch thực tế - `demo-thuc-te`) | Ghi chú |
|---|---|---|---|
| **raw_records** | 247 | 247 | Tổng số dòng đọc từ tệp thô gốc. |
| **cleaned_records** | 46 | 38 | Số bản ghi vượt qua bộ lọc làm sạch để nạp vào ChromaDB. |
| **quarantine_records** | 201 | 209 | Số bản ghi lỗi bị cách ly ra tệp quarantine. |
| **Expectation halt?** | **FAIL** (Bị bypass qua tham số `--skip-validate`) | **PASS** (Tất cả 9 expectations vượt qua) | Phiên chạy trước bị halt do vi phạm kiểm định ngày phép và thời gian hoàn tiền. |

---

## 2. So sánh Kiểm định Retrieval (Before vs After)

Việc làm sạch và làm giàu ngữ cảnh (Enrichment) đã giải quyết triệt để lỗi thông tin sai lệch khi truy vấn cơ sở tri thức (RAG).

### 2a. Chính sách cửa sổ hoàn tiền (`q_refund_window`)
* **Câu hỏi:** *Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền kể từ khi đơn được xác nhận?*
* **Trước (Chưa lọc stale):**
  * **Top-1 Preview:** `Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn.`
  * **Chỉ số:** `contains_expected: yes` | `hits_forbidden: yes` | `top1_doc_expected: yes`
  * **Đánh giá:** Lỗi nghiêm trọng do chứa từ khóa cấm `"14 ngày"` (chính sách cũ đã hết hiệu lực).
* **Sau (Đã áp dụng rule R4 & R6):**
  * **Top-1 Preview:** `Yêu cầu được gửi trong vòng 7 ngày làm việc làm việc kể từ thời điểm xác nhận đơn hàng.`
  * **Chỉ số:** `contains_expected: yes` | `hits_forbidden: no` | `top1_doc_expected: yes`
  * **Đánh giá:** Chính xác tuyệt đối, thông tin hoàn tiền v4 (7 ngày) đã thay thế hoàn toàn thông tin stale.

### 2b. Chính sách ngày phép năm của HR (`q_hr_annual_leave_under3`)
* **Câu hỏi:** *Nhân viên dưới 3 năm kinh nghiệm được bao nhiêu ngày phép năm?*
* **Trước (Chưa lọc stale):**
  * Hệ thống truy xuất được tài liệu HR cũ năm 2025 với nội dung: `Nhân viên dưới 3 năm kinh nghiệm được hưởng 10 ngày phép năm.`
* **Sau (Đã áp dụng rule R7 loại bỏ phiên bản cũ):**
  * **Top-1 Preview:** `Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026.`
  * **Chỉ số:** `contains_expected: yes` | `hits_forbidden: no` | `top1_doc_expected: yes`

---

## 3. Freshness & Monitor

* **Kết quả đo đạc trên `demo-thuc-te`:** Hệ thống cảnh báo mức `WARN` (Ingest = FAIL, Publish = PASS).
* **Giải thích:**
  * **Publish Boundary (PASS):** Thời gian ghi nhận nạp vector store là `2026-06-10T09:17:28Z` trùng khớp với thời điểm pipeline chạy (độ trễ ~ 0h, nhỏ hơn SLA 24h).
  * **Ingest Boundary (FAIL):** Tập tin thô gốc có mốc kết xuất `exported_at = 2026-04-11T00:00:00Z`, cũ hơn thời điểm chạy gần 2 tháng (trễ `1449.29` giờ). Điều này phản ánh dữ liệu nguồn thô đã lâu không được cập nhật từ hệ thống core DB, cần thông báo cho Ingestion Owner kiểm tra tiến trình export tự động.

---

## 4. Kịch bản Inject Corruption (Sprint 3)

Để kiểm chứng tính chống chịu và khả năng cảnh báo của pipeline, chúng tôi đã chạy thử kịch bản phá hủy dữ liệu (Inject Corruption):
* **Lệnh chạy:** `python etl_pipeline.py run --run-id inject-bad --no-refund-fix`
* **Mô tả hành vi:** Pipeline cố tình bỏ qua quy tắc thay thế chính sách hoàn tiền 7 ngày để giữ lại dòng thông tin 14 ngày stale.
* **Cách phát hiện:**
  * Bước validate chạy expectation `refund_no_stale_14d_window` phát hiện có 1 dòng vi phạm chứa từ khóa `"14 ngày"`.
  * Vì luật này có mức độ nghiêm trọng `severity="halt"`, pipeline lập tức chấm dứt tiến trình với mã lỗi exit code `2` và ghi sự kiện `"PIPELINE_HALT"` vào log để ngăn chặn việc ghi dữ liệu bẩn vào ChromaDB.

---

## 5. Hạn chế & việc chưa làm

1. **Kiểm tra ngữ nghĩa sâu (Semantic Validation):** Hiện tại pipeline mới chỉ kiểm tra biểu thức chính quy (Regex) và từ khóa chính để loại bỏ stale. Khi tài liệu nguồn thay đổi cấu trúc hành văn phức tạp, regex có thể bị lỗi thời.
2. **Khôi phục tự động (Auto-recovery):** Khi Ingest Freshness FAIL, hệ thống mới chỉ đưa ra cảnh báo log/slack chứ chưa tự động trigger một yêu cầu xuất dữ liệu mới (pull request) từ DB nguồn.
