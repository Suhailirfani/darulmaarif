from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('register/', views.register_view, name='register'),
    path('success/<int:pk>/', views.register_success, name='register_success'),
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/student/', views.student_dashboard_view, name='student_dashboard'),
    path('dashboard/mentor/', views.mentor_dashboard_view, name='mentor_dashboard'),
    path('classroom/<int:class_id>/', views.classroom_view, name='classroom'),
    path('export/excel/', views.export_excel_view, name='export_excel'),
]
