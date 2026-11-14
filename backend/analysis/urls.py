
from django.urls import path
from .views import cells_list

urlpatterns = [
    path("cells/", cells_list, name="cells-list"),
]
