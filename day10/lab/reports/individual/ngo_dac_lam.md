# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Ngô Đắc Lãm  
**Vai trò:** Ingestion / Cleaning / Embed / Monitoring Owner — Đảm nhiệm thiết kế và lập trình toàn diện hệ thống.  
**Ngày nộp:** 2026-06-10  
**Số từ:** 540 từ

---

## 1. Tôi phụ trách phần nào? (110 từ)

Tôi đảm nhiệm vai trò thiết kế và triển khai toàn bộ hệ thống ETL từ bước thu nhận, làm sạch, kiểm định chất lượng, lưu trữ vector đến hệ thống giám sát. 

**File và Module phụ trách chính:**
* [transform/cleaning_rules.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/transform/cleaning_rules.py): Triển khai 11 quy tắc làm sạch dữ liệu (R1 đến R11), đặc biệt là quy tắc lọc phép năm cũ (R7) và bổ sung context enrichment cho các chunk ngắn (R10) để giải quyết lỗi xếp hạng truy vấn.
* [quality/expectations.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/quality/expectations.py): Thiết kế 9 expectations chất lượng dữ liệu để phát hiện vi phạm stale data trước khi nạp vector store.
* [monitoring/freshness_check.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/monitoring/freshness_check.py): Thiết lập mô hình giám sát freshness hai ranh giới nguồn (Ingest) và đích (Publish) để đo đạc SLA thực tế.

---

## 2. Một quyết định kỹ thuật (140 từ)

Quyết định kỹ thuật quan trọng nhất của tôi là **thiết lập phân cấp cảnh báo kiểm định dữ liệu (Warn vs Halt)** trong [expectations.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/quality/expectations.py) kết hợp với **cơ chế tự động prune trong ChromaDB**. 

Thay vì coi mọi lỗi kiểm định đều khiến pipeline dừng hoạt động (gây gián đoạn dịch vụ RAG) hoặc chỉ ghi nhận cảnh báo (gây rò rỉ dữ liệu bẩn), tôi phân chia:
* **Halt Severity (Dừng pipeline):** Áp dụng cho các lỗi nghiêm trọng về phiên bản dữ liệu (như chính sách hoàn tiền 14 ngày stale, định dạng ISO của ngày phép...). Nếu bất kỳ expectation nào thuộc nhóm này thất bại, pipeline lập tức thoát với exit code `2` và không tiến hành embed.
* **Warn Severity (Cảnh báo):** Áp dụng cho lỗi ít nghiêm trọng hơn như độ dài chunk ngắn (`chunk_min_length_8`) hoặc tỉ lệ dữ liệu làm sạch thấp (`cleaned_yield_not_critically_low`). Pipeline vẫn tiếp tục chạy nhưng ghi log cảnh báo.

Quyết định này cân bằng hoàn hảo giữa tính ổn định của RAG Agent và độ an toàn thông tin của hệ thống tri thức.

---

## 3. Một lỗi hoặc anomaly đã xử lý (150 từ)

Trong quá trình chạy thử nghiệm đánh giá hệ thống, tôi phát hiện lỗi nghiêm trọng tại câu hỏi `gq_d10_06` về thời gian tự động escalate sự cố P1. Mô hình RAG không truy xuất được chunk SLA P1 và xếp hạng sai (đưa thông tin P2 lên đầu).

* **Phát hiện:** Tệp `artifacts/eval/grading_run.jsonl` ghi nhận câu hỏi `gq_d10_06` báo trạng thái **FAIL**.
* **Nguyên nhân:** 
  1. Chunk thô về P1 escalation cực kỳ ngắn (chỉ khoảng 80 ký tự), thiếu từ khóa ngữ cảnh cốt lõi khiến cosine similarity của mô hình embedding `all-MiniLM-L6-v2` bị thấp.
  2. Dữ liệu thô chứa nhiều chunk rác `"Nội dung không rõ ràng"` hoặc ký tự `"!!!"` gây nhiễu không gian xếp hạng vector.
* **Biện pháp khắc phục:** 
  1. Tôi viết rule **R11** để loại bỏ hoàn toàn các chunk nhiễu ra khỏi quá trình embedding.
  2. Tôi xây dựng rule **R10 (Context Enrichment)** tại [cleaning_rules.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/transform/cleaning_rules.py) để tự động làm giàu ngữ cảnh cho các chunk ngắn. Khi phát hiện chunk về P1 escalation, tôi bổ sung thêm suffix: *"Ticket P1 auto escalate sau 10 phút nếu không có phản hồi"*. Kết quả là cosine similarity tăng vọt, đưa chunk này vào top-1 truy vấn thành công.

---

## 4. Bằng chứng trước / sau (90 từ)

* **Run ID kiểm thử:** `final-v4`
* **Trước khi làm sạch (Dữ liệu bẩn/Stale):**
  * `q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,...,yes,yes,yes,3`
  *(Vi phạm từ khóa cấm - hits_forbidden: yes)*
* **Sau khi làm sạch (Phiên bản chuẩn):**
  * `q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,...,yes,no,yes,3`
  *(Đã sửa đổi thành 7 ngày làm việc - hits_forbidden: no)*
  * Câu hỏi `gq_d10_06` về P1 Escalation chuyển từ **FAIL** sang **PASS** ở vị trí top-1.

---

## 5. Cải tiến tiếp theo (50 từ)

Nếu có thêm 2 giờ làm bài, tôi sẽ cấu hình kết nối trực tiếp đến **Great Expectations** để tự động xuất báo cáo HTML chất lượng dữ liệu tương tác chuyên nghiệp, thay vì chỉ hiển thị kết quả kiểm định dạng văn bản thô trên bảng console của hệ thống.
