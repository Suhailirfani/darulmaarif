from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('register/', views.register_view, name='register'),
    path('success/<int:pk>/', views.register_success, name='register_success'),
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/admin/classes/', views.admin_manage_class_view, name='admin_manage_class'),
    path('dashboard/admin/mentors/', views.admin_manage_mentor_view, name='admin_manage_mentor'),
    path('dashboard/admin/assign/', views.admin_assign_students_view, name='admin_assign_students'),
    path('dashboard/admin/verify-payment/', views.admin_verify_payment_view, name='admin_verify_payment'),
    path('dashboard/admin/edit-registration/', views.admin_edit_registration_view, name='admin_edit_registration'),
    path('dashboard/admin/toggle-lock/', views.admin_toggle_lock_view, name='admin_toggle_lock'),
    path('dashboard/student/', views.student_dashboard_view, name='student_dashboard'),
    path('dashboard/mentor/', views.mentor_dashboard_view, name='mentor_dashboard'),
    path('classroom/<int:class_id>/', views.classroom_view, name='classroom'),
    path('export/excel/', views.export_excel_view, name='export_excel'),
]
