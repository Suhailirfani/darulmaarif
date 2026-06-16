from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('register/', views.register_view, name='register'),
    path('success/<int:pk>/', views.register_success, name='register_success'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('export/excel/', views.export_excel_view, name='export_excel'),
]
