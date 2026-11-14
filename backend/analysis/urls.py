
from django.urls import path

from .views import (
    cells_list,
    statistics_view,
    geojson_view,
    available_dates_view,
    coverage_view,
    temporal_view,
    audit_view,
    comparison_view,
    pilot_comparisons_view
)

urlpatterns = [
    path("cells/", cells_list, name="cells-list"),
    path(
        "statistics/",
        statistics_view,
        name="statistics",
    ),
    path(
        "geojson/",
        geojson_view,
        name="geojson",
    ),
    path(
        "available-dates/",
        available_dates_view,
        name="available-dates",
    ),
    path(
        "coverage/",
        coverage_view,
        name="coverage",
    ),
    path(
        "temporal/",
        temporal_view,
        name="temporal",
    ),
    path(
        "audit/",
        audit_view,
        name="audit",
    ),
    path(
        "comparison/",
        comparison_view,
        name="comparison",
    ),
    path(
        "pilot-comparisons/",
        pilot_comparisons_view,
        name="pilot-comparisons",
    ),
]
