from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class Customer(models.Model):
    name = models.CharField("Tên khách hàng", max_length=200)
    phone = models.CharField("Số điện thoại", max_length=20, blank=True)

    class Meta:
        verbose_name = "Khách hàng"
        verbose_name_plural = "Khách hàng"

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField("Tên mặt hàng", max_length=200)

    class Meta:
        verbose_name = "Mặt hàng"
        verbose_name_plural = "Mặt hàng"

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Mới"
        DELIVERED = "DELIVERED", "Đã giao"
        CANCELLED = "CANCELLED", "Hủy"

    # Luồng trạng thái: trạng thái hiện tại -> các trạng thái được phép chuyển tới.
    # Muốn đổi luồng (vd thêm "Hoàn trả") thì chỉ cần sửa bảng này.
    ALLOWED_TRANSITIONS = {
        Status.NEW: {Status.DELIVERED, Status.CANCELLED},
        Status.DELIVERED: set(),
        Status.CANCELLED: set(),
    }

    # PROTECT: không xoá được khách hàng / mặt hàng khi đã có đơn tham chiếu tới.
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders", verbose_name="Khách hàng"
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="orders", verbose_name="Mặt hàng"
    )
    # Lớp 1: validator báo lỗi rõ ràng cho người dùng (chạy trong full_clean).
    quantity = models.IntegerField(
        "Số lượng", validators=[MinValueValidator(1, "Số lượng phải lớn hơn 0.")]
    )
    unit_price = models.DecimalField(
        "Đơn giá",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), "Đơn giá phải lớn hơn 0.")],
    )
    # editable=False: không xuất hiện trên form, client không nhập được. Giá trị do save() tính.
    total = models.DecimalField(
        "Thành tiền", max_digits=18, decimal_places=2, editable=False, default=Decimal("0")
    )
    status = models.CharField(
        "Trạng thái", max_length=20, choices=Status.choices, default=Status.NEW
    )
    # Dùng default=timezone.now (thay vì auto_now_add) để seed/test tạo được đơn ở ngày cũ;
    # editable=False nên người dùng vẫn không sửa được trên form.
    created_at = models.DateTimeField("Ngày tạo", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Đơn hàng"
        verbose_name_plural = "Đơn hàng"
        ordering = ["-created_at"]
        # Lớp 2: ràng buộc ở database, chặn cả khi bỏ qua code Python (vd QuerySet.update).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="order_quantity_gt_0",
                violation_error_message="Số lượng phải lớn hơn 0.",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0),
                name="order_unit_price_gt_0",
                violation_error_message="Đơn giá phải lớn hơn 0.",
            ),
        ]

    def __str__(self):
        return f"Đơn #{self.pk}"

    # ---------- Tính toán ----------

    def calculate_total(self):
        """Thành tiền = số lượng × đơn giá, tính bằng Decimal để không sai số làm tròn."""
        try:
            return Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
        except InvalidOperation:
            # Số lượng/đơn giá để trống hoặc sai kiểu: full_clean() sẽ báo lỗi ở đúng trường đó.
            return Decimal("0")

    # ---------- Kiểm tra nghiệp vụ ----------

    def _get_original(self):
        """Bản gốc đang lưu trong database, hoặc None nếu đây là đơn mới."""
        if self.pk is None:
            return None
        return Order.objects.filter(pk=self.pk).first()

    def _changed_fields(self, original):
        """Tên các trường khác với bản gốc (bỏ qua id, và total vì do server tự tính)."""
        return [
            field.name
            for field in self._meta.concrete_fields
            if field.name not in ("id", "total")
            and getattr(self, field.attname) != getattr(original, field.attname)
        ]

    def clean(self):
        super().clean()
        # Lỗi ở đây dùng dạng non-field (không gắn vào trường cụ thể) vì có form không hiển thị
        # trường status; gắn lỗi vào trường không có trên form sẽ làm ModelForm báo ValueError.
        original = self._get_original()

        # Tạo mới: bắt buộc trạng thái Mới, không tạo thẳng được đơn Đã giao / Hủy.
        if original is None:
            if self.status != self.Status.NEW:
                raise ValidationError("Đơn mới tạo phải ở trạng thái “Mới”.")
            return

        # Sửa: so với BẢN GỐC trong database, không tin trạng thái đang nằm trong bộ nhớ.
        changed = self._changed_fields(original)
        other_changed = [name for name in changed if name != "status"]

        # Quy tắc 1: chỉ đơn còn ở trạng thái Mới mới được sửa thông tin.
        if other_changed and original.status != self.Status.NEW:
            raise ValidationError(
                f"Đơn đang ở trạng thái “{original.get_status_display()}”, không thể sửa nữa."
            )

        # Quy tắc 2: đổi trạng thái phải nằm trong ALLOWED_TRANSITIONS.
        # Đã giao / Hủy có tập rỗng nên mọi lần đổi trạng thái từ đó đều bị từ chối.
        if "status" in changed:
            allowed = self.ALLOWED_TRANSITIONS.get(original.status, set())
            if self.status not in allowed:
                raise ValidationError(
                    f"Không thể chuyển trạng thái từ “{original.get_status_display()}” "
                    f"sang “{self.get_status_display()}”."
                )

    # ---------- Ghi dữ liệu ----------

    def save(self, *args, **kwargs):
        # 1) Server tự tính thành tiền, ghi đè mọi giá trị total client gửi lên.
        self.total = self.calculate_total()

        # Nếu gọi save(update_fields=[...]) thì vẫn phải ghi total để không bị lệch.
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"total"}

        # 2) Transaction: khoá dòng + kiểm tra + ghi diễn ra như một khối duy nhất.
        with transaction.atomic():
            if self.pk is not None:
                # 3) Khoá dòng đơn hàng tới hết transaction: người thứ 2 phải chờ người thứ 1
                #    ghi xong, rồi clean() mới đọc bản gốc (đã cập nhật) để kiểm tra.
                #    Lưu ý: SQLite không hỗ trợ nên lệnh này bị bỏ qua; PostgreSQL thì có tác dụng.
                list(Order.objects.select_for_update().filter(pk=self.pk))

            # 4) Gọi full_clean trong save() để quy tắc áp dụng cho MỌI đường ghi
            #    (Admin, shell, test...), không chỉ qua form.
            self.full_clean()

            # 5) Lưu.
            super().save(*args, **kwargs)

    def change_status(self, new_status):
        """Đổi trạng thái. Bị từ chối thì trả lại trạng thái cũ trong bộ nhớ rồi ném lỗi."""
        old_status = self.status
        if new_status == old_status:
            raise ValidationError(f"Đơn đã ở trạng thái “{self.get_status_display()}” rồi.")

        self.status = new_status
        try:
            self.save()
        except ValidationError:
            self.status = old_status
            raise
