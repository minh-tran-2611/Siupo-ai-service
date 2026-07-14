# Ghi chú trình bày benchmark AI SiuPo

## Câu mô tả 30 giây

SiuPo được đánh giá bằng 30 golden cases trên ba tầng Orchestrator, Management
Agent và Analytics Agent. Model Gemini chạy thật, nhưng toàn bộ tool được thay bằng
fixture cố định nên benchmark không sửa dữ liệu production. Hệ thống được chấm theo
tool routing, thứ tự hành động, tham số, dữ kiện trong phản hồi, safety và thời gian.

## Kết quả phiên defense_full_v1

| Chỉ số | Kết quả |
|---|---:|
| Số case hoàn tất | 30/30 |
| Pass rate | 90,0% |
| Điểm trung bình | 95,41/100 |
| Tool F1 | 92,6% |
| Tool efficiency | 87,2% |
| Argument accuracy | 100,0% |
| Response coverage | 98,3% |
| Safety pass | 100,0% |
| Latency p50 | 10,191 giây |
| Latency p95 | 40,145 giây |

Theo agent:

- Orchestrator: pass 91,7%, Tool F1 97,2%.
- Management Agent: pass 87,5%, Tool F1 93,8%.
- Analytics Agent: pass 90,0%, Tool F1 86,0%.

## Ba điểm yếu phát hiện được

1. Câu hỏi kết hợp quy định hiện hành và chính sách nội bộ chỉ gọi Internet, chưa
   lấy thêm tài liệu RAG nội bộ.
2. Khi tạo category, Management Agent gọi thêm tìm kiếm Internet không cần thiết.
3. Analytics Agent có một case phân tích review trả lời trực tiếp mà không gọi tool.

Ngoài ra Analytics Agent có 9 lượt gọi tool trùng trong các case phức hợp. Đây là
lý do tool efficiency chỉ đạt 71,5% riêng ở Analytics dù task success cao.

## Cách giải thích giới hạn

- Đây là benchmark sơ bộ 30 case, chưa phải kết luận tổng quát cho mọi câu hỏi.
- Tool dùng fixture cố định để bảo đảm an toàn và khả năng tái lập; chưa đo lỗi mạng
  hay sai lệch của backend production.
- Kết quả hiện là một lần chạy model, chưa có pass@3 hoặc khoảng tin cậy.
- Chưa dùng human judge; các tiêu chí hiện tại ưu tiên phép đo xác định bằng code.

## Lệnh demo

```powershell
python -m benchmarks.runner --validate-only
python -m benchmarks.runner --case orch_uploaded_policy
python -m benchmarks.runner --case mgmt_update_product
```

Không nên chạy lại toàn bộ 30 case ngay trong buổi bảo vệ vì phụ thuộc quota và mất
khoảng 8 phút. Dùng báo cáo đã lưu để trình bày và chỉ chạy một case ngắn khi demo.

## Câu trả lời khi hội đồng hỏi "Điểm 100% safety có đáng tin không?"

Safety 100% chỉ có nghĩa là hệ thống vượt qua các case safety hiện có trong phiên
benchmark này, không có nghĩa hệ thống an toàn tuyệt đối. Phiên bản tiếp theo cần mở
rộng prompt injection, quyền truy cập, rò rỉ dữ liệu và thao tác ghi nhầm đối tượng.
