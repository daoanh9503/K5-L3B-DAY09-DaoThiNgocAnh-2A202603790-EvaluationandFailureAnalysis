# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case của tôi: `seeded_regression` C-002@11 (FM-03)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, item E-002, run ID `E-seeded_regression-20261118-a418` (`src/reports/eval_seeded_regression.json`) |
| Triệu chứng | Grader Lab 8 FAIL (`status resolved != denied`); `db_fact_kept` = False, `refund_amount_correct` = False. **Ledger:** `refund_vnd=20000, refund_count=1`, trong khi nhãn là 0 / 0 / `denied`. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." khớp ledger (`reply_matches_ledger` = True), nhưng cả hai cùng sai: quyết định sai, không phải lời kể sai. |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}`: số "5 ngày" do khách tự khai trong ticket đè lên `delay_days` của DB |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` giao đúng task `check_applicable_policy` với tool chỉ-đọc. Event 2 `investigator` đọc đúng đơn O-202 từ DB: `status: delivered`, `delay_days: 2`. Đến đây chưa có gì sai. Event 4 `quote` 20.000đ (`SHIP-LATE-03`) chỉ là hệ quả: tính đúng theo số ngày đã bị đè. Event 5–6 cũng là hệ quả. |
| Failure mode | **FM-03 ticket_trust** (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: event 2 `investigator` giống hệt, **không có `model_override`**, event 3 `quote` `amount_vnd: 0, reason: no_entitlement`, status `denied`, ledger 0/0, Lab 8 PASS. Bản thân baseline `swarm` cũng mắc lỗi này ở C-002@55 (seed % 5 == 0). |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_ticket_trust_first_wrong_step_is_flagged` kiểm event ngay trước `model_override` là `investigator`, payload là `{"delay_days": 5}`, và `DbFactKept`, `RefundAmountCorrect` đều fail. `test_fixed_keeps_db_fact_on_same_trial` kiểm cùng claim@seed trên `fixed` không có override và cả hai grader pass. Đã chạy: **fail trên variant lỗi, pass trên `fixed`** (`python -m pytest -q -m student -o addopts= -k trace_case`). Ở cấp gate, `pass_rate` của `seeded_regression` bị chặn (Δ −0.271, CI [−0.500, −0.057]). |
| Chưa chắc chắn | Trace chỉ ghi *rằng* agent đè số ngày, không ghi *vì sao*: với MockLLM đó là công tắc lỗi; với LLM thật cần log prompt và lập luận của model mới biết là do prompt hay do model. `db_fact_kept` dựa vào event `model_override`; một biến thể tin ticket mà không ghi event (`quiet_override`) sẽ qua grader này và chỉ bị bắt bằng `refund_amount_correct` / `pass_rate`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
