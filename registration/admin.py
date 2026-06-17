from django.contrib import admin
from .models import Registration, UserProfile, CourseClass, StudentProgress

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('application_number', 'name', 'mobile', 'is_paid', 'created_at')
    list_filter = ('is_paid',)
    search_fields = ('name', 'mobile', 'district')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'mentor')
    list_filter = ('role',)

@admin.register(CourseClass)
class CourseClassAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'youtube_video_id')
    ordering = ('order',)

@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'course_class', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'course_class')
    search_fields = ('student__username',)
