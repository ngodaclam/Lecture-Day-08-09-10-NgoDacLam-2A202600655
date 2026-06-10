# Data Contract & Schema Specification — Lab Day 10

**Nhóm:** Team NgoDacLam-2A202600655  
**Cập nhật:** 2026-06-10

Tài liệu này đặc tả Data Contract được thống nhất giữa nhóm kỹ sư dữ liệu và các hệ thống tiêu dùng (multi-agent RAG) nhằm bảo vệ tính toàn vẹn của dữ liệu trong cơ sở tri thức (Knowledge Base).

---

## 1. Nguồn Dữ Liệu (Source Map)

Hệ thống thu nhận dữ liệu từ 5 nguồn tài liệu chính thống sau đây:

| Nguồn (doc_id) | Phương thức Ingest | Failure Mode chính | Chỉ số giám sát / Alert |
|---|---|---|---|
| **policy_refund_v4** | File CSV thô chứa xuất bản | Bản ghi chứa thông tin cửa sổ hoàn tiền cũ (14 ngày) | Đếm số bản ghi vi phạm `no_stale_refund_window` → Halt |
| **sla_p1_2026** | File CSV thô chứa xuất bản | Nội dung P1 escalation ngắn quá không đủ ngữ cảnh | Check độ dài chunk tối thiểu (`chunk_min_length_8`) → Warn |
| **it_helpdesk_faq** | File CSV thô chứa xuất bản | Các dòng dữ liệu trống hoặc trùng lặp văn bản | Lọc trùng (`duplicate_chunk_text`) → Quarantine |
| **hr_leave_policy** | File CSV thô chứa xuất bản | Bản ghi chứa số ngày phép cũ năm 2025 (10 ngày phép) | Lọc ngày phép cũ (`stale_hr_policy_effective_date`) → Quarantine |
| **access_control_sop** | File CSV thô chứa xuất bản | Tài liệu chưa được phê duyệt hoặc thiếu trong whitelist | Kiểm tra tài liệu lạ (`unknown_doc_id`) → Quarantine |

---

## 2. Đặc tả Schema Cleaned

Sau khi đi qua các quy tắc làm sạch, dữ liệu đầu ra xuất ra file cleaned CSV và ChromaDB bắt buộc phải tuân thủ schema sau:

| Thuộc tính (Column) | Kiểu dữ liệu | Bắt buộc | Mô tả & Ràng buộc |
|---|---|---|---|
| **chunk_id** | String | Có | Khóa chính của chunk, được định nghĩa dưới dạng: `{doc_id}#{dòng thô xuất phát}#{số thứ tự chunk}` nhằm phục vụ idempotency. |
| **doc_id** | String | Có | Khóa logic của tài liệu nguồn (nằm trong whitelist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`). |
| **chunk_text** | String | Có | Nội dung đoạn văn bản đã được làm sạch, loại bỏ ký tự đặc biệt thừa, tối thiểu 8 ký tự. |
| **effective_date** | Date (ISO 8601) | Có | Ngày có hiệu lực của chính sách, định dạng: `YYYY-MM-DD`. Không chấp nhận ngày rỗng hoặc sai định dạng. |
| **exported_at** | Datetime (ISO) | Có | Thời điểm dữ liệu được kết xuất từ hệ thống nguồn thô. Dùng để đo độ tươi (Freshness) ở Ingest Boundary. |

---

## 3. Quy tắc Quarantine vs Drop

* **Hành vi cách ly (Quarantine):** Bất kỳ bản ghi thô nào vi phạm các quy tắc chất lượng dữ liệu cơ bản (như: doc_id lạ, trùng lặp nội dung, ngày phép cũ, text rác, thiếu thông tin bắt buộc) sẽ **không bị drop âm thầm** mà được tách ra và đẩy vào tệp `artifacts/quarantine/quarantine_{run_id}.csv`.
* **Phân tích nguyên nhân:** Tệp quarantine lưu kèm cột `reason` và thông tin thô để phục vụ điều tra lỗi.
* **Quy trình xử lý:**
  1. Data Engineer định kỳ kiểm tra các tệp quarantine.
  2. Nếu phát hiện quarantine nhầm (như trường hợp tài liệu hợp lệ `access_control_sop` bị quarantine do thiếu trong whitelist ban đầu), kỹ sư tiến hành cập nhật Data Contract và cleaning rules để mở rộng whitelist.
  3. Dữ liệu sau khi sửa đổi contract sẽ được tái xử lý (re-run) để bổ sung vào vector store.

---

## 4. Phiên bản & Canonical (Source of Truth)

Để tránh xung đột thông tin giữa các tài liệu cũ và mới:
* **Chính sách hoàn tiền (Refund):** Chỉ chấp nhận bản ghi thuộc tài liệu `policy_refund_v4`. Mọi dữ liệu trỏ tới phiên bản cũ (v3, v2...) hoặc chứa giá trị hoàn tiền 14 ngày (thay vì 7 ngày của v4) đều bị coi là lỗi thời và pipeline sẽ dừng ngay lập tức (halt) khi phát hiện.
* **Chính sách ngày phép năm (Annual Leave):** Chỉ chấp nhận các bản ghi có hiệu lực từ ngày **2026-01-01** trở đi (quy định tối thiểu 12 ngày phép). Các bản ghi phép năm cũ (chỉ 10 ngày phép của bản 2025) sẽ bị cách ly.
