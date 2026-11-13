from django.urls import path

from .views import FromSourceView

app_name = 'ai_import'

urlpatterns = [
    path('from-source/', FromSourceView.as_view(), name='from_source'),
]
