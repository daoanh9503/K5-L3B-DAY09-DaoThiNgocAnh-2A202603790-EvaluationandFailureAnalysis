# Judge audit

Chạy (trong `src/`): `python -m lab9.judge --csv <file> --audit 5`. Judge chạy ở chế độ replay: verdict đã lưu sẵn trong CSV, không cần key.
Lớp dương là **FAIL**, vì việc của judge là tìm ra reply hỏng.

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Tỉ lệ FAIL quan sát → hiệu chỉnh RG | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **Đạt** (exit 0) | **dùng** (non-blocking, kèm hiệu chỉnh RG) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **Không đạt** κ và R (exit 1) | **loại**, không dùng làm gate |

Rogan-Gladen: `(p_obs + spec − 1) / (sens + spec − 1)`, với sens = recall và spec = tn/(tn+fp).
Với helpful, spec = 70/70 = 1.0 nên tỉ lệ hiệu chỉnh = 0.09 / 0.30 = 0.30. Con số này khớp tỉ lệ FAIL thật theo người (30/100):
judge nhìn thấy chưa tới một phần ba số reply hỏng.

## Audit thủ công các bất đồng
Đã đọc hết 10 bất đồng của tone và 21 của helpful. Dưới đây là những case đại diện cho từng kiểu lỗi.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người** | Judge coi xưng "em/anh" + "nha" là thân thiện. Rubric thêm: *xưng hô phải là "LogiX" với "anh/chị"; "em", "bạn", "nha", "nhé" là FAIL.* (Cùng kiểu: H-017.) |
| 2 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | **Người** | Judge bị kính ngữ "Dạ, vui lòng" ở đầu câu đánh lừa. Rubric: *đánh giá cả câu; câu mệnh lệnh hoặc chặn khách liên hệ là FAIL dù có kính ngữ.* |
| 3 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric: *xin lỗi không bắt buộc khi yêu cầu đã được xử lý; ngắn nhưng đủ ý là PASS.* |
| 4 | tone H-051 "…LogiX đã refund 90.000đ…" | FAIL | PASS | **Người** | Style guide CS LogiX cho phép từ "refund". Rubric thêm whitelist thuật ngữ (refund, ship, COD). |
| 5 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Người đọc nhầm ticket. **Sửa nhãn người** thành FAIL trong bản nhãn tiếp theo, không sửa rubric. Đây là lý do audit phải hai chiều: nhãn người không phải chân lý tuyệt đối. |
| 6 | tone H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người** | Lời hứa vượt quá kết quả hệ thống. Đây không phải lỗi giọng văn mà là lỗi nội dung. Rubric tone thêm: *không hứa hành động mà hệ thống chưa ghi nhận.* Kiểm bằng code thì chắc hơn. |
| 7 | tone H-070 "…ạ 😂😂", H-094 "Da, LogiX da hoan…" | PASS | FAIL | **Người** | Rubric: *emoji cười trong khiếu nại là FAIL; tiếng Việt mất dấu là FAIL.* |
| 8 | tone H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | **Người** (chấp nhận được) | Lỗi gõ lặp từ, không xúc phạm khách. Rubric: *lỗi chính tả nhỏ không đổi nghĩa thì không FAIL tone.* |
| 9 | helpful HL-016 (xin lỗi dài) "…LogiX đã hoàn 55.000đ cho đơn O-404…" (ledger 35.000đ) | PASS | FAIL | **Người** | Judge chỉ thấy văn bản, **không thấy ledger**, và bị câu xin lỗi dài thuyết phục (verbosity bias). Cả **18/18** reply "sai tiền" đều lọt. Đây chính là FM-08: phải chấm bằng code so reply với ledger, không sửa được bằng rubric. |
| 10 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | **Người** | Reply ngắn, lịch sự, sai số tiền. Judge không có dữ liệu để biết. Như #9. |
| 11 | helpful HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Sai xưng hô, lọt cả 3/3 case. Thuộc tiêu chí tone (judge tone sẽ bắt), không nên gộp vào helpful. Rubric helpful: *tách hẳn tone ra khỏi helpful.* |

## Kết luận
- **tone_ok dùng được**: κ = 0.757, P = 0.857, R = 0.8, đều trên sàn. Ta vẫn chỉ dùng nó làm metric **non-blocking**,
  báo tỉ lệ FAIL đã hiệu chỉnh RG (0.28 → 0.30), vì judge bỏ sót 6/30 reply hỏng
  (đa số là xưng hô suồng sã hoặc kính ngữ che giọng ra lệnh) và báo nhầm 4/70.
  Sau khi sửa rubric theo các case 1–8 và sửa nhãn H-081, cần calibrate lại trên một tập nhãn mới.
- **helpful bị loại khỏi gate**: R = 0.30 < 0.7 và κ = 0.375 < 0.6.
  Precision = 1.0 trông đẹp nhưng gây hiểu lầm: judge gần như chỉ bắt reply rõ ràng lạc đề hoặc cụt
  (giọng cụt 4/4, không hỏi lại mã đơn 3/3, lạc đề 2/2), còn **bỏ sót toàn bộ 18 reply sai tiền** và 3 reply sai xưng hô.
  Nếu dùng làm gate, tỉ lệ FAIL quan sát 0.09 sẽ báo một agent tệ gấp ba lần thực tế là "tốt".
  Thay thế: số tiền dùng code grader FM-08 (reply vs ledger, M3); xưng hô dùng judge tone; phần còn lại của helpful
  (hỏi lại mã đơn, đúng chủ đề) viết rubric hẹp hơn rồi calibrate lại.
- **Nguyên tắc rút ra**: tiền và approval luôn chấm bằng code. Judge chỉ dùng cho tiêu chí chủ quan,
  và chỉ khi đã qua sàn trên nhãn người.
- **Rủi ro còn lại**: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 reply mỗi tiêu chí), nên các con số
  có thể bị overfit vào tập này. Cần nhãn người mới làm held-out thật. Nhãn người cũng có lỗi (H-081),
  nên cần ≥2 người gán nhãn và đo κ giữa người với người trước khi coi đó là chân lý.
