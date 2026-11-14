
from django.urls import path

from .views import (
    cells_list,
    statistics_view,
    geojson_view,
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
]
