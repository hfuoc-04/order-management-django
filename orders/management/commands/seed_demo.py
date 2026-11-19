from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Customer, Item, Order

CUSTOMERS = [
    ("Nguyễn Văn An", "0901234567"),
    ("Trần Thị Bình", "0912345678"),
    ("Lê Hoàng Cường", ""),
    ("Công ty TNHH Minh Phát", "02838123456"),
]

ITEMS = ["Bút bi", "Vở 200 trang", "Giấy A4 (ram)", "Bìa hồ sơ"]

# (số ngày trước hôm nay, giờ, phút, khách, mặt hàng, số lượng, đơn giá, trạng thái)
D, C, N = Order.Status.DELIVERED, Order.Status.CANCELLED, Order.Status.NEW
ORDERS = [
    (6, 9, 0, 0, 0, 10, "5000", D),
    (6, 14, 15, 1, 2, 2, "75000", D),
    (5, 10, 30, 2, 1, 5, "12000", C),
    (4, 8, 45, 3, 2, 20, "72000", D),
    (4, 16, 0, 0, 3, 15, "3000", D),
    (3, 23, 30, 1, 0, 4, "5000", D),   # 23h30: vẫn tính vào ngày này
    (2, 0, 30, 2, 1, 3, "12000", D),   # 0h30: theo UTC sẽ là ngày hôm trước, báo cáo vẫn tính đúng ngày
    (2, 11, 0, 3, 3, 50, "2500", C),
    (1, 9, 15, 0, 2, 1, "75000", D),
    (1, 15, 40, 1, 1, 6, "12000", N),
    (1, 17, 20, 2, 0, 8, "5000", N),
]


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu: khách hàng, mặt hàng và đơn ở nhiều ngày, nhiều trạng thái."

    @transaction.atomic
    def handle(self, *args, **options):
        customer_names = [name for name, _ in CUSTOMERS]
        # Chạy lại lần nữa thì không tạo trùng; không đụng tới dữ liệu khác trong database.
        if Order.objects.filter(customer__name__in=customer_names).exists():
            self.stdout.write(self.style.WARNING("Đã có dữ liệu mẫu, không tạo thêm."))
            return

        customers = [Customer.objects.get_or_create(name=name, defaults={"phone": phone})[0]
                     for name, phone in CUSTOMERS]
        items = [Item.objects.get_or_create(name=name)[0] for name in ITEMS]

        today = timezone.localdate()
        for days_ago, hour, minute, c, i, quantity, price, status in ORDERS:
            created_at = timezone.make_aware(
                datetime.combine(today - timedelta(days=days_ago), time(hour, minute))
            )
            order = Order(customer=customers[c], item=items[i], quantity=quantity,
                          unit_price=Decimal(price), created_at=created_at)
            order.save()
            # Đi đúng luồng nghiệp vụ: tạo ở trạng thái Mới rồi mới chuyển trạng thái.
            if status != Order.Status.NEW:
                order.change_status(status)

        self.stdout.write(self.style.SUCCESS(
            f"Đã tạo {len(customers)} khách hàng, {len(items)} mặt hàng, {len(ORDERS)} đơn hàng."
        ))
