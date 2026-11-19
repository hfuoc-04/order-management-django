from django import forms


class DateRangeForm(forms.Form):
    """Bộ lọc từ ngày / đến ngày cho báo cáo. Cả hai đều không bắt buộc."""

    # type="date" để trình duyệt hiện lịch chọn ngày; trình duyệt gửi lên dạng YYYY-MM-DD.
    date_from = forms.DateField(
        label="Từ ngày",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    date_to = forms.DateField(
        label="Đến ngày",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def clean(self):
        cleaned = super().clean()
        date_from, date_to = cleaned.get("date_from"), cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("“Từ ngày” không được sau “Đến ngày”.")
        return cleaned
