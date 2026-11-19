from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Item, Order
from .reports import daily_revenue

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class OrderTestCase(TestCase):
    """Lớp cha: tạo sẵn 1 khách hàng, 1 mặt hàng và hàm tạo đơn cho các test bên dưới."""

    def setUp(self):
        self.customer = Customer.objects.create(name="Khách A")
        self.item = Item.objects.create(name="Bút bi")

    def make_order(self, quantity=3, unit_price="15000", status=None, created_at=None):
        order = Order(customer=self.customer, item=self.item,
                      quantity=quantity, unit_price=Decimal(unit_price))
        if created_at is not None:
            order.created_at = created_at
        order.save()
        # Đơn luôn được tạo ở trạng thái Mới, muốn trạng thái khác thì phải đi đúng luồng.
        if status is not None and status != Order.Status.NEW:
            order.change_status(status)
        return order


# ---------- Thành tiền ----------

class TotalTests(OrderTestCase):
    def test_total_is_quantity_times_unit_price(self):
        order = self.make_order(quantity=3, unit_price="15000")
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("45000"))

    def test_total_sent_by_client_is_ignored(self):
        order = Order(customer=self.customer, item=self.item,
                      quantity=3, unit_price=Decimal("15000"), total=Decimal("1"))
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("45000"))

    def test_total_is_recalculated_when_quantity_changes(self):
        order = self.make_order(quantity=3, unit_price="15000")
        order.quantity = 4
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("60000"))


# ---------- Số lượng và đơn giá > 0 ----------

class PositiveValueTests(OrderTestCase):
    def assert_rejected(self, field, **values):
        with self.assertRaises(ValidationError) as ctx:
            self.make_order(**values)
        self.assertIn(field, ctx.exception.message_dict)
        self.assertEqual(Order.objects.count(), 0)

    def test_quantity_zero_is_rejected(self):
        self.assert_rejected("quantity", quantity=0)

    def test_quantity_negative_is_rejected(self):
        self.assert_rejected("quantity", quantity=-1)

    def test_unit_price_zero_is_rejected(self):
        self.assert_rejected("unit_price", unit_price="0")

    def test_unit_price_negative_is_rejected(self):
        self.assert_rejected("unit_price", unit_price="-1000")

    # QuerySet.update() bỏ qua save()/full_clean(), nên chỉ còn ràng buộc CHECK của database chặn.
    # atomic() bên trong để lỗi database không làm hỏng transaction của cả test.
    def test_database_rejects_quantity_zero(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.filter(pk=order.pk).update(quantity=0)

    def test_database_rejects_quantity_negative(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.filter(pk=order.pk).update(quantity=-5)

    def test_database_rejects_unit_price_zero(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.filter(pk=order.pk).update(unit_price=0)

    def test_database_rejects_unit_price_negative(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.filter(pk=order.pk).update(unit_price=-1000)


# ---------- Trạng thái khi tạo đơn ----------

class NewOrderStatusTests(OrderTestCase):
    def test_new_order_has_status_new(self):
        order = self.make_order()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_cannot_create_order_as_delivered(self):
        order = Order(customer=self.customer, item=self.item, quantity=1,
                      unit_price=Decimal("1000"), status=Order.Status.DELIVERED)
        with self.assertRaises(ValidationError):
            order.save()
        self.assertEqual(Order.objects.count(), 0)


# ---------- Chuyển trạng thái ----------

class StatusTransitionTests(OrderTestCase):
    def test_new_to_delivered_succeeds(self):
        order = self.make_order()
        order.change_status(Order.Status.DELIVERED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_new_to_cancelled_succeeds(self):
        order = self.make_order()
        order.change_status(Order.Status.CANCELLED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def assert_transition_rejected(self, start, target):
        order = self.make_order(status=start)
        with self.assertRaises(ValidationError):
            order.change_status(target)
        # Trạng thái trong bộ nhớ được trả lại như cũ...
        self.assertEqual(order.status, start)
        # ...và trong database cũng không đổi.
        order.refresh_from_db()
        self.assertEqual(order.status, start)

    def test_delivered_to_cancelled_is_rejected(self):
        self.assert_transition_rejected(Order.Status.DELIVERED, Order.Status.CANCELLED)

    def test_cancelled_to_delivered_is_rejected(self):
        self.assert_transition_rejected(Order.Status.CANCELLED, Order.Status.DELIVERED)

    def test_delivered_to_new_is_rejected(self):
        self.assert_transition_rejected(Order.Status.DELIVERED, Order.Status.NEW)


# ---------- Khoá sửa đơn đã giao / đã hủy ----------

class LockedOrderTests(OrderTestCase):
    def assert_quantity_change_rejected(self, status):
        order = self.make_order(quantity=3, status=status)
        order.quantity = 10
        with self.assertRaises(ValidationError):
            order.save()
        order.refresh_from_db()
        self.assertEqual(order.quantity, 3)
        self.assertEqual(order.total, Decimal("45000"))

    def test_cannot_change_quantity_of_delivered_order(self):
        self.assert_quantity_change_rejected(Order.Status.DELIVERED)

    def test_cannot_change_quantity_of_cancelled_order(self):
        self.assert_quantity_change_rejected(Order.Status.CANCELLED)


# ---------- Báo cáo doanh thu theo ngày ----------

class DailyRevenueReportTests(OrderTestCase):
    def rows(self, **filters):
        return [(r["day"], r["order_count"], r["revenue"]) for r in daily_revenue(**filters)]

    def test_only_delivered_orders_are_counted(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=VN)
        self.make_order(quantity=1, unit_price="10000", status=Order.Status.DELIVERED, created_at=at)
        self.make_order(quantity=1, unit_price="20000", status=Order.Status.NEW, created_at=at)
        self.make_order(quantity=1, unit_price="40000", status=Order.Status.CANCELLED, created_at=at)
        self.assertEqual(self.rows(), [(date(2026, 11, 17), 1, Decimal("10000"))])

    def test_groups_by_creation_date_newest_first(self):
        delivered = Order.Status.DELIVERED
        self.make_order(1, "10000", delivered, datetime(2026, 11, 17, 8, 0, tzinfo=VN))
        self.make_order(2, "5000", delivered, datetime(2026, 11, 17, 20, 0, tzinfo=VN))
        self.make_order(1, "7000", delivered, datetime(2026, 11, 18, 9, 0, tzinfo=VN))
        self.assertEqual(self.rows(), [
            (date(2026, 11, 18), 1, Decimal("7000")),
            (date(2026, 11, 17), 2, Decimal("20000")),
        ])

    def test_order_at_23h30_vietnam_time_counts_on_that_day(self):
        self.make_order(1, "3000", Order.Status.DELIVERED, datetime(2026, 11, 18, 23, 30, tzinfo=VN))
        self.assertEqual(self.rows(), [(date(2026, 11, 18), 1, Decimal("3000"))])

    # 0h30 ngày 19/11 giờ VN = 17h30 ngày 18/11 giờ UTC: nếu gom theo UTC sẽ bị tính nhầm sang 18/11.
    def test_order_at_00h30_vietnam_time_is_not_moved_to_previous_utc_day(self):
        self.make_order(1, "7000", Order.Status.DELIVERED, datetime(2026, 11, 19, 0, 30, tzinfo=VN))
        self.assertEqual(self.rows(), [(date(2026, 11, 19), 1, Decimal("7000"))])

    def test_day_without_delivered_orders_has_no_row(self):
        self.make_order(1, "10000", Order.Status.DELIVERED, datetime(2026, 11, 17, 10, 0, tzinfo=VN))
        self.make_order(1, "10000", Order.Status.CANCELLED, datetime(2026, 11, 16, 10, 0, tzinfo=VN))
        self.make_order(1, "10000", Order.Status.NEW, datetime(2026, 11, 15, 10, 0, tzinfo=VN))
        days = [day for day, _, _ in self.rows()]
        self.assertEqual(days, [date(2026, 11, 17)])

    def test_date_filter_keeps_both_ends(self):
        delivered = Order.Status.DELIVERED
        for day in (16, 17, 18, 19):
            self.make_order(1, "1000", delivered, datetime(2026, 11, day, 12, 0, tzinfo=VN))
        days = [d for d, _, _ in self.rows(date_from=date(2026, 11, 17), date_to=date(2026, 11, 18))]
        self.assertEqual(days, [date(2026, 11, 18), date(2026, 11, 17)])


class DailyRevenueViewTests(OrderTestCase):
    url = reverse("orders:daily_revenue")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_user_sees_report(self):
        self.make_order(3, "15000", Order.Status.DELIVERED, datetime(2026, 11, 17, 10, 0, tzinfo=VN))
        self.client.force_login(User.objects.create_user("nhanvien", password="x", is_staff=True))
        response = self.client.get(self.url)
        self.assertContains(response, "17/11/2026")
        self.assertContains(response, "45.000")

    def test_empty_report_shows_message(self):
        self.client.force_login(User.objects.create_user("nhanvien", password="x", is_staff=True))
        self.assertContains(self.client.get(self.url), "Chưa có doanh thu")


# ---------- Admin action đổi trạng thái hàng loạt ----------

class AdminBulkActionTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_superuser("admin", "", "x"))

    def test_bulk_cancel_with_mixed_orders(self):
        new_1 = self.make_order()
        new_2 = self.make_order()
        delivered = self.make_order(status=Order.Status.DELIVERED)

        response = self.client.post(reverse("admin:orders_order_changelist"), {
            "action": "mark_cancelled",
            "_selected_action": [new_1.pk, new_2.pk, delivered.pk],
        })

        # Đơn hợp lệ đổi được sang Hủy...
        for order in (new_1, new_2):
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.CANCELLED)
        # ...đơn không hợp lệ giữ nguyên, không làm hỏng các đơn còn lại.
        delivered.refresh_from_db()
        self.assertEqual(delivered.status, Order.Status.DELIVERED)

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any(str(delivered) in t for t in texts))   # báo lỗi đúng đơn bị chặn
        self.assertTrue(any("Đã chuyển 2 đơn" in t for t in texts))
