"""URL routing — async views + OpenAPI docs (doc 08 §8.3)."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    # Recommended: governed, name-based invocation (no raw SQL from clients).
    path("v1/datasources/<str:name>/view", views.view_query_view),
    path("v1/datasources/<str:name>/function", views.function_view),
    path("v1/datasources/<str:name>/procedure", views.procedure_view),
    # Advanced/trusted: raw parameterized SQL.
    path("v1/datasources/<str:name>/query", views.query_view),
    path("v1/datasources/<str:name>/execute", views.execute_view),
    # Admin / docs.
    path("v1/datasources", views.datasources_view),
    path("v1/health", views.health_view),
    path("openapi.json", views.openapi_view),
    path("docs/", views.docs_view),
]
