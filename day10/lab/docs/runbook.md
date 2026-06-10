# Runbook — Xử lý Sự Cố Chất Lượng Dữ Liệu & Thất Thoát Thông Tin

**Nhóm:** Team NgoDacLam-2A202600655  
**Cập nhật:** 2026-06-10

Tài liệu này hướng dẫn quy trình vận hành và xử lý sự cố (Incident Response) khi hệ thống giám sát dữ liệu RAG phát hiện lỗi hoặc người dùng phản ánh thông tin sai lệch.

---

## 1. Triệu chứng (Symptom)

* **Phản ánh từ người dùng:** Hệ thống AI Agent/Chatbot trả lời sai lệch thông tin chính sách, ví dụ:
  * Trả lời thời hạn hoàn tiền là `"14 ngày"` (trong khi chính sách đúng là 7 ngày).
  * Trả lời số ngày phép năm là `"10 ngày"` đối với nhân sự dưới 3 năm kinh nghiệm (trong khi đúng phải là 12 ngày).
  * Trả lời sai thời gian tự động escalate sự cố P1 hoặc không tìm thấy quy trình cấp quyền truy cập `access_control_sop`.
* **Phản ánh từ hệ thống tự động:** File đánh giá chất lượng retrieval báo điểm thấp hoặc các câu hỏi đánh giá tự động (Grading Questions) bị trượt (Fail).

---

## 2. Phát hiện (Detection)

Sự cố được phát hiện tự động qua các kênh giám sát sau:
1. **Pipeline Halt (Dừng khẩn cấp):** Lệnh chạy pipeline kết thúc với exit code `2` và ghi nhận sự kiện `"PIPELINE_HALT"` do vi phạm luật có thuộc tính `severity="halt"` trong [expectations.py](file:///c:/Users/LocND/Desktop/api/Lecture-Day-08-09-10-NgoDacLam-2A202600655/day10/lab/quality/expectations.py).
2. **Freshness Alert (Cảnh báo độ tươi):** Công cụ check freshness báo trạng thái `FAIL` trên kênh Slack `#alerts-data-pipeline` do dữ liệu nguồn đầu vào trễ quá 24.0h.
3. **Retrieval Eval Alert:** Lệnh chạy `python eval_retrieval.py` cho thấy cột `contains_expected` có giá trị `"no"` hoặc `hits_forbidden` có giá trị `"yes"`.

---

## 3. Chẩn đoán (Diagnosis)

Khi phát hiện sự cố, quản trị viên thực hiện chẩn đoán theo các bước sau:

| Bước | Hành động | Kết quả kiểm tra mong đợi | Ý nghĩa chẩn đoán |
|---|---|---|---|
| **1** | Mở tệp manifest gần nhất: `artifacts/manifests/manifest_{run_id}.json` | Xem trường `expectations` xem luật nào bị `passed: false`. | Xác định chính xác lỗi kiểm định (ví dụ: phát hiện bản ghi hoàn tiền stale). |
| **2** | Kiểm tra tệp cách ly lỗi: `artifacts/quarantine/quarantine_{run_id}.csv` | Tìm kiếm các cột chứa lỗi và đọc lý do tại cột `reason`. | Biết được dữ liệu bị loại bỏ do trùng lặp (`duplicate_chunk_text`), ngày phép cũ (`stale_hr_policy_effective_date`), hay doc_id lạ (`unknown_doc_id`). |
| **3** | Chạy đánh giá retrieval cục bộ: `python eval_retrieval.py` | Kiểm tra kết quả ghi nhận tại `artifacts/eval/before_after_eval.csv`. | Xác định xem lỗi do mô hình Embedding xếp hạng sai (RAG ranking issue) hay do dữ liệu sạch bị lọc thiếu. |

---

## 4. Khắc phục tạm thời (Mitigation)

1. **Rollback Embed (Nếu đẩy dữ liệu lỗi lên ChromaDB):**
   * Nếu pipeline chạy với tùy chọn `--skip-validate` làm dữ liệu lỗi lọt vào ChromaDB, thực hiện chạy lại pipeline chuẩn bằng lệnh:
     ```powershell
     python etl_pipeline.py run --run-id recovery-run
     ```
     Cơ chế *Pruning* tự động của pipeline sẽ xóa sạch các vector lỗi thời và khôi phục trạng thái chuẩn của dữ liệu.
2. **Xử lý Quarantine nhầm:**
   * Nếu tài liệu hợp lệ bị quarantine do thiếu trong whitelist (như `access_control_sop`), hãy mở rộng whitelist trong `transform/cleaning_rules.py` và `contracts/data_contract.yaml`, sau đó rerun lại pipeline.

---

## 5. Phòng ngừa lâu dài (Prevention)

1. **Khóa cứng Pipeline:** Luôn chạy pipeline ở chế độ mặc định (không truyền tham số `--skip-validate`) để đảm bảo không một bản ghi lỗi nào có thể lọt vào vector store khi chưa vượt qua 9 expectations chất lượng.
2. **Cập nhật Cắt giảm Phiên bản (Cutoff date):** Không hard-code các ngày cắt giảm phiên bản trong code. Đưa biến `hr_leave_min_effective_date` vào `data_contract.yaml` hoặc biến môi trường `.env` để quản lý tập trung và thay đổi nhanh chóng khi có chính sách mới.
3. **Giám sát Freshness định kỳ:** Thiết lập cron-job chạy lệnh kiểm tra freshness mỗi 6 tiếng một lần để cảnh báo sớm nếu hệ thống trích xuất dữ liệu thô bị ngắt kết nối.
