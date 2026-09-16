import os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Registration(models.Model):
    name = models.CharField(max_length=255)
    house_name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    post = models.CharField(max_length=255)
    pin_code = models.CharField(max_length=15, blank=True, default="")
    district = models.CharField(max_length=255)
    mobile = models.CharField(max_length=20)
    whatsapp = models.CharField(max_length=20)
    is_paid = models.BooleanField(default=False)
    transaction_time_and_date = models.DateTimeField(blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    screenshot = models.ImageField(upload_to='screenshots/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    application_num = models.PositiveIntegerField(unique=True, null=True, blank=True)

    @property
    def application_number(self):
        return f"{self.application_num:03d}" if self.application_num else ""

    @property
    def screenshot_exists(self):
        if self.screenshot and hasattr(self.screenshot, 'path'):
            try:
                return os.path.isfile(self.screenshot.path)
            except Exception:
                return False
        return False

    def save(self, *args, **kwargs):
        if not self.application_num:
            # Find the smallest available positive integer gap starting from 1
            existing_numbers = set(Registration.objects.values_list('application_num', flat=True))
            num = 1
            while num in existing_numbers:
                num += 1
            self.application_num = num
        super().save(*args, **kwargs)

    def __str__(self):
        return f"APP-{self.application_number} : {self.name} - {self.mobile}"

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('MENTOR', 'Mentor'),
        ('STUDENT', 'Student'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT')
    registration = models.OneToOneField(Registration, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_profile')
    mentor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'MENTOR'}, related_name='mentees')

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

class CourseClass(models.Model):
    title = models.CharField(max_length=255)
    youtube_video_id = models.CharField(max_length=50, help_text="The ID from the YouTube URL (e.g. dQw4w9WgXcQ)")
    order = models.PositiveIntegerField(unique=True, help_text="The sequence number of the class")
    description = models.TextField(blank=True)
    publish_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when class is displayed to students (blank for immediate display)")

    class Meta:
        ordering = ['order']

    @property
    def thumbnail_url(self):
        if self.youtube_video_id:
            return f"https://img.youtube.com/vi/{self.youtube_video_id}/hqdefault.jpg"
        return ""

    @property
    def is_published(self):
        if self.publish_at:
            from django.utils import timezone
            return timezone.now() >= self.publish_at
        return True

    def __str__(self):
        return f"Class {self.order}: {self.title}"

class StudentProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress')
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='student_progress')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course_class')

    def __str__(self):
        return f"{self.student.username} - {self.course_class.title} - {'Completed' if self.is_completed else 'Pending'}"

# Signal to auto-create User when Registration is_paid becomes True or sync details
@receiver(post_save, sender=Registration)
def create_student_user(sender, instance, created, **kwargs):
    if getattr(instance, '_skip_user_sync', False):
        return

    if instance.is_paid:
        # Check if student profile already exists for this registration
        profile = UserProfile.objects.filter(registration=instance).first()
        if profile:
            # Profile exists, sync user details if updated
            user = profile.user
            updated = False
            if user.first_name != instance.name:
                user.first_name = instance.name
                updated = True
            if not getattr(instance, '_skip_username_sync', False):
                if user.username != instance.mobile:
                    # Only update username if target mobile isn't taken by another user
                    conflicting_user = User.objects.filter(username=instance.mobile).exclude(pk=user.pk).first()
                    if conflicting_user:
                        # Clear out conflicting user/profile if it's an orphaned duplicate
                        UserProfile.objects.filter(user=conflicting_user).exclude(pk=profile.pk).delete()
                        conflicting_user.delete()
                    user.username = instance.mobile
                    updated = True
            if updated:
                user.save()
            return

        # If no profile exists yet for this registration, check if User with username=instance.mobile exists
        user = User.objects.filter(username=instance.mobile).first()
        if not user:
            user = User.objects.create_user(
                username=instance.mobile,
                password=f"APP-{instance.application_number}",
                first_name=instance.name
            )
        else:
            if user.first_name != instance.name:
                user.first_name = instance.name
                user.save()
        
        # Ensure no other profile holds this registration (1-to-1 constraint)
        UserProfile.objects.filter(registration=instance).exclude(user=user).update(registration=None)

        # Link user and profile
        profile = UserProfile.objects.filter(user=user).first()
        if not profile:
            UserProfile.objects.create(
                user=user,
                role='STUDENT',
                registration=instance
            )
        else:
            if profile.registration != instance:
                profile.registration = instance
                profile.save()

class AppSetting(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value_bool = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.key}: {self.value_bool}"

