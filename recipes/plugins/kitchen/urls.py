from django.urls import path

from .views import CookedView, PickerView

app_name = 'kitchen'

urlpatterns = [
    path('', PickerView.as_view(), name='picker'),
    path('gekocht/', CookedView.as_view(), name='cooked'),
]
