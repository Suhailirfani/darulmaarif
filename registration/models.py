from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Registration(models.Model):
    name = models.CharField(max_length=255)
    house_name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    post = models.CharField(max_length=255)
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

    class Meta:
        ordering = ['order']

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

# Signal to auto-create User when Registration is_paid becomes True
@receiver(post_save, sender=Registration)
def create_student_user(sender, instance, created, **kwargs):
    if instance.is_paid:
        # Check if user already exists
        if not User.objects.filter(username=instance.mobile).exists():
            # Create User
            user = User.objects.create_user(
                username=instance.mobile,
                password=f"APP-{instance.application_number}",
                first_name=instance.name
            )
            # Create UserProfile
            UserProfile.objects.create(
                user=user,
                role='STUDENT',
                registration=instance
            )

class AppSetting(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value_bool = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.key}: {self.value_bool}"

