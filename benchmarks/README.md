# SiuPo AI Benchmark

Benchmark này chạy model Gemini thật nhưng thay toàn bộ tool bằng fixture. Vì vậy
có thể đo quyết định routing, tool calling và câu trả lời mà không ghi dữ liệu thật,
không gửi email/Zalo và không gọi backend quản trị.

## Chạy nhanh

```powershell
python -m benchmarks.runner --validate-only
python -m benchmarks.runner --targets orchestrator --limit 5
python -m benchmarks.runner
```

Kết quả được lưu tại `benchmarks/results/<run_id>/report.md` và `results.json`.

Phiên dùng cho bảo vệ hiện nằm tại `results/defense_full_v1/report.md`. Xem
`DEFENSE_NOTES.md` để lấy số liệu slide, giới hạn và câu trả lời phản biện.

## Ý nghĩa chỉ số

- `Tool F1`: agent có chọn đủ tool cần thiết và tránh tool thừa hay không.
- `Argument accuracy`: tham số bắt buộc có đúng không.
- `Response coverage`: câu trả lời có chứa dữ kiện bắt buộc không.
- `Safety pass`: không gọi tool bị cấm trong case.
- `Order match`: chuỗi tool bắt buộc có xuất hiện đúng thứ tự không.
- `Pass rate`: case đạt ít nhất 80 điểm, đủ tool bắt buộc và không vi phạm safety.

## Quy tắc an toàn

Không đưa tool production vào runner. `FixtureRuntime` thay mapping tool ngay trước
khi gọi agent và khôi phục trong `finally`. Chỉ dùng database/Qdrant thật nếu sau này
xây thêm bộ E2E riêng với tài khoản và collection test.

## Thêm case

Mỗi dòng trong `datasets/golden_v1.jsonl` là một JSON object. Các trường chính:

- `target`: `orchestrator`, `management` hoặc `analytics`.
- `expected_tools`: chuỗi tool bắt buộc.
- `expected_args`: subset tham số cần khớp.
- `forbidden_tools`: tool không được gọi.
- `response_terms`: mỗi nhóm chỉ cần khớp một cách diễn đạt.

Không thay đổi dataset sau khi xem kết quả chỉ để tăng điểm. Khi cập nhật tiêu chí,
tạo `golden_v2.jsonl` để kết quả benchmark có thể tái lập.
