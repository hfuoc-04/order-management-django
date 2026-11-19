# Quản lý đơn hàng (Django)

App nhỏ quản lý đơn hàng. Dùng Python 3.11, Django 5.2, SQLite; giao diện là Django Admin.

## Cách cài và chạy

Yêu cầu: Python 3.11 trở lên.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # tạo tài khoản đăng nhập
python manage.py seed_demo            # (tuỳ chọn) tạo dữ liệu mẫu
python manage.py runserver
```

- Quản lý đơn hàng: http://127.0.0.1:8000/admin/
- Báo cáo doanh thu theo ngày: http://127.0.0.1:8000/reports/daily-revenue/ (hoặc bấm nút "Báo cáo doanh thu" trên trang danh sách đơn hàng)
- Chạy test: `python manage.py test orders`

## Đã làm theo đề

1. **Đơn hàng** gồm khách hàng, mặt hàng, số lượng, đơn giá, thành tiền. Mỗi đơn một mặt hàng.
2. **Thành tiền:**
   - Server tự tính bằng số lượng × đơn giá mỗi lần lưu. Giá trị thành tiền gửi lên đều bị bỏ qua.
   - Số lượng và đơn giá phải lớn hơn 0. Điều kiện này được kiểm tra ở model, và database cũng có ràng buộc `CHECK`.
3. **Trạng thái:**
   - Đơn mới tạo luôn ở trạng thái Mới.
   - Từ Mới chỉ chuyển được sang Đã giao hoặc Hủy.
   - Đơn Đã giao hoặc Hủy thì không sửa và không đổi trạng thái được nữa.
   - Quy tắc nằm ở model nên áp dụng cho mọi nơi lưu đơn. Trên giao diện, đơn đã chốt chỉ xem được.
4. **Báo cáo doanh thu theo ngày:**
   - Mỗi ngày một dòng, gồm số đơn và tổng thành tiền.
   - Chỉ tính đơn Đã giao, gom theo ngày tạo đơn.
5. **Giao diện:** Django Admin. Có tạo, sửa và đổi trạng thái từng đơn hoặc nhiều đơn cùng lúc, cùng trang báo cáo.

Ngoài ra còn có test tự động (`orders/tests.py`) cho các quy tắc trên.

## Các giả định

- Đề ưu tiên Frappe nhưng cho phép framework quen thuộc, nên em dùng Django. Django Admin đóng vai trò tương tự màn hình Desk của Frappe.
- Khách hàng và mặt hàng là hai danh mục riêng; khi tạo đơn thì chọn từ danh sách. Số điện thoại khách hàng không bắt buộc.
- Đơn giá nhập tay khi tạo đơn, vì đề không nói mặt hàng có giá cố định.
- Tiền tính bằng VND, lưu kiểu số thập phân với 2 chữ số sau dấu phẩy.
- Ngày tạo đơn là thời điểm lưu đơn lần đầu, không sửa được. Báo cáo lấy ngày theo giờ Việt Nam.
- Ngày không có đơn Đã giao thì báo cáo không có dòng cho ngày đó.
- Đổi sang đúng trạng thái hiện tại (ví dụ Mới → Mới) bị coi là không hợp lệ và báo lỗi.
- Đề không nói về xoá đơn, nên phần này giữ nguyên mặc định của Django Admin.

## Phần chưa làm

- Chưa làm bằng Frappe, framework được đề ưu tiên.
- Quy tắc trạng thái được kiểm tra khi lưu đơn qua model. Nếu cập nhật thẳng vào database (ví dụ `QuerySet.update()`) thì vẫn đổi được trạng thái của đơn đã chốt. Riêng số lượng và đơn giá vẫn bị database chặn nếu ≤ 0.
