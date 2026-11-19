from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .forms import DateRangeForm
from .reports import daily_revenue


# Chỉ nhân viên (is_staff) đã đăng nhập mới xem được; chưa đăng nhập thì chuyển về trang login của Admin.
@staff_member_required
def daily_revenue_report(request):
    form = DateRangeForm(request.GET)  # không có tham số nào -> hợp lệ, không lọc
    rows = daily_revenue(**form.cleaned_data) if form.is_valid() else []

    context = {
        **admin.site.each_context(request),  # biến chung của Admin: tiêu đề site, user, menu...
        "title": "Báo cáo doanh thu theo ngày",
        "form": form,
        "rows": rows,
    }
    return render(request, "orders/daily_revenue.html", context)
