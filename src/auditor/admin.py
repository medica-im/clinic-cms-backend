from django.contrib import admin
from django.utils import timezone
from datetime import datetime

from .models import OIDC


class IATRangeFilter(admin.SimpleListFilter):
    title = 'Issued at (range)'
    parameter_name = 'iat_range'
    template = 'admin/filters/iat_range_filter.html'

    def lookups(self, request, model_admin):
        return ()

    def choices(self, changelist):
        # Provide the default "All" choice and let our template render inputs
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string({}, []),
            'display': 'All',
        }

    def queryset(self, request, queryset):
        after = request.GET.get('iat_after')
        before = request.GET.get('iat_before')

        def _to_timestamp(value):
            try:
                # Expecting an ISO-local value from <input type="datetime-local">
                dt = datetime.fromisoformat(value)
            except Exception:
                return None
            if dt.tzinfo is None:
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return int(dt.timestamp())

        if after:
            ts = _to_timestamp(after)
            if ts is not None:
                queryset = queryset.filter(iat__gte=ts)

        if before:
            ts = _to_timestamp(before)
            if ts is not None:
                queryset = queryset.filter(iat__lte=ts)

        return queryset


class OIDCAdmin(admin.ModelAdmin):
    list_display = ('email', 'sub', 'iss', 'aud', 'site')
    search_fields = ('email', 'sub')
    list_filter = ('site', IATRangeFilter)


admin.site.register(OIDC, OIDCAdmin)