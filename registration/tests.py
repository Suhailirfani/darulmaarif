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

    def test_student_login_and_dashboard_access(self):
        # Login with student credentials
        login_success = self.client.login(username='9876543210', password=f"APP-{self.reg.application_number}")
        self.assertTrue(login_success)

        # Access dashboard router
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('student_dashboard'))

        # Access student dashboard page
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Classroom')

    def test_student_without_userprofile_auto_heals_and_reaches_dashboard(self):
        # Create a user with no UserProfile attached (e.g. created manually or orphaned)
        orphan_user = User.objects.create_user(
            username='9988776655',
            password='password123',
            first_name='Orphan Student'
        )
        self.assertFalse(hasattr(orphan_user, 'profile'))

        # Login as orphan user
        self.client.login(username='9988776655', password='password123')

        # Access dashboard router -> should self-heal profile and redirect to student_dashboard (not landing)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('student_dashboard'))

        # Verify profile was automatically created
        orphan_user.refresh_from_db()
        self.assertTrue(hasattr(orphan_user, 'profile'))
        self.assertEqual(orphan_user.profile.role, 'STUDENT')

        # Directly hitting student_dashboard also renders successfully without redirecting to landing
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Classroom')

    def test_phone_changed_student_login_and_dashboard_flow(self):
        # Admin changes mobile of student
        self.client.login(username='admin_test', password='password123')
        self.client.post(reverse('admin_edit_registration'), {
            'reg_id': self.reg.id,
            'name': 'Updated Name',
            'mobile': '9111222333',
            'house_name': 'Test House',
            'place': 'Test Place',
            'post': 'Test Post',
            'pin_code': '673001',
            'district': 'Calicut',
            'whatsapp': '9111222333',
        })
        self.client.logout()

        # Student logs in with new mobile number
        login_success = self.client.login(username='9111222333', password=f"APP-{self.reg.application_number}")
        self.assertTrue(login_success)

        # Student reaches dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('student_dashboard'))

        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Classroom')


