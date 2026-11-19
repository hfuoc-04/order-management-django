from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect

from .models import Customer, Item, Order

admin.site.site_header = "Quản lý đơn hàng"
admin.site.site_title = "Quản lý đơn hàng"
admin.site.index_title = "Trang quản trị"


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone")
    search_fields = ("name", "phone")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "customer", "item", "quantity", "unit_price", "total", "status", "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("customer__name",)
    list_select_related = ("customer", "item")  # tránh N+1 query khi hiện tên khách/mặt hàng
    actions = ["mark_delivered", "mark_cancelled"]

    ADD_FIELDS = ("customer", "item", "quantity", "unit_price")
    CHANGE_FIELDS = ADD_FIELDS + ("total", "status", "created_at")

    # ---------- Form ----------

    def get_fields(self, request, obj=None):
        # Form tạo đơn: không có status (model mặc định là Mới), không có total (server tự tính).
        if obj is None:
            return self.ADD_FIELDS
        return self.CHANGE_FIELDS

    def get_readonly_fields(self, request, obj=None):
        # total và created_at chỉ hiển thị, không cho nhập.
        if obj is None:
            return ()
        return ("total", "created_at")

    def has_change_permission(self, request, obj=None):
        # Đơn đã giao / đã hủy: chỉ cho xem. Admin sẽ tự hiện MỌI trường ở chế độ chỉ đọc,
        # ẩn nút Lưu và từ chối (403) nếu ai đó cố POST. Model vẫn tự chặn thêm một lớp.
        if obj is not None and not obj.is_editable:
            return False
        return super().has_change_permission(request, obj)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # Thông thường lỗi nghiệp vụ đã được form bắt và hiện ngay trên form.
        # Đây là lưới an toàn cho lỗi phát sinh lúc save(), ví dụ người khác vừa đổi trạng thái
        # đơn này: hiện thông báo thay vì trang lỗi 500. Transaction của Admin đã rollback.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as e:
            self.message_user(request, " ".join(e.messages), messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    # ---------- Actions đổi trạng thái hàng loạt ----------

    @admin.action(description="Đánh dấu Đã giao")
    def mark_delivered(self, request, queryset):
        self._change_status_many(request, queryset, Order.Status.DELIVERED)

    @admin.action(description="Hủy đơn")
    def mark_cancelled(self, request, queryset):
        self._change_status_many(request, queryset, Order.Status.CANCELLED)

    def _change_status_many(self, request, queryset, new_status):
        # Không dùng queryset.update() vì nó bỏ qua save() và mọi kiểm tra nghiệp vụ.
        # Đổi TỪNG đơn qua change_status(); mỗi đơn là một transaction riêng nên
        # đơn lỗi không làm hỏng các đơn khác.
        success = 0
        for order in queryset.order_by("pk"):
            try:
                order.change_status(new_status)
                success += 1
            except ValidationError as e:
                self.message_user(request, f"{order}: {' '.join(e.messages)}", messages.ERROR)

        if success:
            self.message_user(
                request,
                f"Đã chuyển {success} đơn sang “{new_status.label}”.",
                messages.SUCCESS,
            )
