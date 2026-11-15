
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
    pilot_comparisons_view,
    firms_detections_view
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
    path(
        "firms-detections/",
        firms_detections_view,
        name="firms-detections",
    ),
]

# Versioned public scientific API: PostgreSQL only. Legacy analysis routes remain available.
from . import api
urlpatterns += [
    path('health/', api.health),
    path('v1/regions/', api.regions),
    path('v1/dates/', api.dates),
    path('v1/observations/', api.Observations.as_view()),
    path('v1/observations/<int:pk>/', api.Observation.as_view()),
    path('v1/summary/', api.summary),
    path('v1/map/', api.map_view),
]

from . import detections_api
urlpatterns += [path("v1/detections/", detections_api.detections), path("v1/sensors/", detections_api.sensors)]

urlpatterns += [
    path('v1/detections/summary/', detections_api.detections),
    path('v1/detections/dates/', detections_api.dates),
    path('v1/harmonization/', api.Observations.as_view()),
    path('v1/harmonization/cells/', api.map_view),
    path('v1/harmonization/summary/', api.summary),
]

urlpatterns += [path('v1/harmonization/runs/', api.scientific_runs), path('v1/harmonization/versions/', api.runs)]
