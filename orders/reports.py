from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Order


def daily_revenue(date_from=None, date_to=None):
    """Doanh thu theo ngày: mỗi ngày một dòng gồm số đơn và tổng thành tiền.

    - Chỉ tính đơn Đã giao.
    - Gom theo NGÀY TẠO đơn, tính theo giờ Việt Nam.
    - date_from / date_to (kiểu date, không bắt buộc): lọc theo khoảng ngày, tính cả 2 đầu.
    - Ngày mới nhất lên đầu.
    """
    orders = Order.objects.filter(status=Order.Status.DELIVERED).annotate(
        # created_at lưu giờ UTC: phải đổi sang giờ Việt Nam rồi mới cắt lấy phần ngày,
        # nếu không đơn tạo lúc 0h30 sáng (giờ VN) sẽ bị tính vào ngày hôm trước.
        # get_default_timezone() = TIME_ZONE trong settings = Asia/Ho_Chi_Minh.
        day=TruncDate("created_at", tzinfo=timezone.get_default_timezone())
    )
    # Lọc trên chính cột "day" đã đổi giờ, để bộ lọc và cách gom dùng cùng một múi giờ.
    if date_from:
        orders = orders.filter(day__gte=date_from)
    if date_to:
        orders = orders.filter(day__lte=date_to)

    return (
        orders.values("day")  # GROUP BY day
        .annotate(order_count=Count("id"), revenue=Sum("total"))
        .order_by("-day")
    )
