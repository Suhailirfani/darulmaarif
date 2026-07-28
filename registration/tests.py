from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from registration.models import Registration, UserProfile

class RegistrationEditTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Create admin user
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            password='password123',
            email='admin@example.com'
        )
        UserProfile.objects.create(user=self.admin_user, role='ADMIN')

        # Create a paid student registration
        self.reg = Registration.objects.create(
            name='Test Student',
            house_name='Test House',
            place='Test Place',
            post='Test Post',
            pin_code='673001',
            district='Calicut',
            mobile='9876543210',
            whatsapp='9876543210',
            is_paid=True
        )

    def test_edit_registration_mobile_update_and_signal_sync(self):
        self.client.login(username='admin_test', password='password123')
        
        # Verify initial User and UserProfile exist
        user = User.objects.get(username='9876543210')
        self.assertEqual(user.first_name, 'Test Student')
        profile = UserProfile.objects.get(registration=self.reg)
        self.assertEqual(profile.user, user)

        # Edit mobile number via admin_edit_registration_view
        response = self.client.post(reverse('admin_edit_registration'), {
            'reg_id': self.reg.id,
            'name': 'Test Student Updated',
            'mobile': '9876543299',
            'house_name': 'Test House',
            'place': 'Test Place',
            'post': 'Test Post',
            'pin_code': '673001',
            'district': 'Calicut',
            'whatsapp': '9876543299',
        })
        self.assertEqual(response.status_code, 302)

        # Refresh from DB
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.mobile, '9876543299')
        self.assertEqual(self.reg.name, 'Test Student Updated')

        # Verify User username was updated to new mobile without throwing IntegrityError
        user.refresh_from_db()
        self.assertEqual(user.username, '9876543299')
        self.assertEqual(user.first_name, 'Test Student Updated')
        
        # Ensure only 1 profile exists for this registration
        self.assertEqual(UserProfile.objects.filter(registration=self.reg).count(), 1)

    def test_service_worker_endpoint(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')

