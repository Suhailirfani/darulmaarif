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
            'screenshot': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_paid = cleaned_data.get('is_paid')
        screenshot = cleaned_data.get('screenshot')

        if is_paid and not screenshot:
            self.add_error('screenshot', 'Screenshot is required when Paid or Not is Yes.')
        
        return cleaned_data
