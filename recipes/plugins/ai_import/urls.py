from django.urls import path

from .preview_views import PreviewView
from .settings_views import SettingsView
from .views import FromSourceView

app_name = 'ai_import'

urlpatterns = [
    path('from-source/', FromSourceView.as_view(), name='from_source'),
    path('settings/', SettingsView.as_view(), name='settings'),
    path('preview/', PreviewView.as_view(), name='preview'),
]
