from django.db import models

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

    def __str__(self):
        return f"{self.name} - {self.mobile}"
