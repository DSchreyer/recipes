from django.urls import path

from .views import PickerView

app_name = 'kitchen'

urlpatterns = [
    path('', PickerView.as_view(), name='picker'),
]
