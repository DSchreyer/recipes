from django.urls import path

from .views import CookedEntryView, CookedView, PickerView

app_name = 'kitchen'

urlpatterns = [
    path('', PickerView.as_view(), name='picker'),
    path('gekocht/', CookedView.as_view(), name='cooked'),
    # One entry of the history: rate, re-date, re-note, delete, cook again.
    path('gekocht/<int:pk>/', CookedEntryView.as_view(), name='cooked_entry'),
]
