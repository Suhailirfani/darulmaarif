from django import forms
from .models import Registration

class RegistrationForm(forms.ModelForm):
    class Meta:
        model = Registration
        fields = [
            'name', 'house_name', 'place', 'post', 'district',
            'mobile', 'whatsapp', 'is_paid', 'transaction_time_and_date',
            'transaction_id', 'screenshot'
        ]
        widgets = {
            'transaction_time_and_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'is_paid': forms.Select(choices=[(False, 'No'), (True, 'Yes')]),
        }
