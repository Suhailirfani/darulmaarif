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

    def test_stale_profile_conflict_resolution(self):
        # Suppose an old user profile holds registration=self.reg
        old_user = User.objects.get(username='9876543210')
        old_profile = UserProfile.objects.get(registration=self.reg)
        self.assertEqual(old_profile.user, old_user)

        # Old user changes or is archived, new user is registered with this mobile
        old_user.username = '9876543210_archived'
        old_user.save()

        new_user = User.objects.create_user(
            username='9876543210',
            password='password123',
            first_name='New User'
        )
        self.client.force_login(new_user)

        # When new_user accesses /dashboard/, it should resolve the registration conflict without raising IntegrityError
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('student_dashboard'))

        # Verify new_user now has the profile linked to self.reg and old_profile was disassociated
        new_user.refresh_from_db()
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertEqual(new_user.profile.registration, self.reg)

        old_profile.refresh_from_db()
        self.assertIsNone(old_profile.registration)

    def test_admin_scheduled_class_display_and_visibility(self):
        from datetime import timedelta
        from django.utils import timezone
        from registration.models import CourseClass

        # Admin creates class 1 (Immediate) and class 2 (Future scheduled)
        class1 = CourseClass.objects.create(
            title='Class 1 Immediate',
            youtube_video_id='vid1',
            order=1,
            publish_at=None
        )
        future_time = timezone.now() + timedelta(days=2)
        class2 = CourseClass.objects.create(
            title='Class 2 Scheduled',
            youtube_video_id='vid2',
            order=2,
            publish_at=future_time
        )

        # Student logs in
        self.client.login(username='9876543210', password=f"APP-{self.reg.application_number}")

        # Student dashboard should show Class 1, but NOT Class 2
        response = self.client.get(reverse('student_dashboard'))
        self.assertContains(response, 'Class 1 Immediate')
        self.assertNotContains(response, 'Class 2 Scheduled')

        # Direct attempt to enter class 2 should redirect back to dashboard
        response = self.client.get(reverse('classroom', args=[class2.id]))
        self.assertRedirects(response, reverse('student_dashboard'))

        # Admin logs in
        self.client.login(username='admin_test', password='password123')

        # Admin viewing student dashboard (preview mode) sees all classes
        response = self.client.get(reverse('student_dashboard'))
        self.assertContains(response, 'Class 1 Immediate')
        self.assertContains(response, 'Class 2 Scheduled')

        # Admin edits class 2 using 12-hour AM/PM fields to release in the past
        past_time = timezone.now() - timedelta(hours=1)
        self.client.post(reverse('admin_manage_class'), {
            'action': 'edit',
            'class_id': class2.id,
            'title': 'Class 2 Scheduled',
            'order': 2,
            'youtube_video_id': 'vid2',
            'publish_date': past_time.strftime('%Y-%m-%d'),
            'publish_hour': past_time.strftime('%I'),
            'publish_minute': past_time.strftime('%M'),
            'publish_ampm': past_time.strftime('%p'),
        })

        # Student logs in again -> now Class 2 is visible
        self.client.login(username='9876543210', password=f"APP-{self.reg.application_number}")
        response = self.client.get(reverse('student_dashboard'))
        self.assertContains(response, 'Class 2 Scheduled')

    def test_user_profile_edit_for_student(self):
        # Student logs in
        self.client.login(username='9876543210', password=f"APP-{self.reg.application_number}")

        # Access profile edit page
        response = self.client.get(reverse('user_profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"APP-{self.reg.application_number}")
        self.assertContains(response, "പ്രൊഫൈൽ വിവരങ്ങൾ തിരുത്തുക")

        # Edit name, mobile, and password
        response = self.client.post(reverse('user_profile_edit'), {
            'name': 'Student Renamed',
            'username': '9876543210_updated',
            'mobile': '9876543210',
            'whatsapp': '9876543210',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123',
        })
        self.assertRedirects(response, reverse('user_profile_edit'))

        # Verify user and registration updated
        user = User.objects.get(username='9876543210_updated')
        self.assertEqual(user.first_name, 'Student Renamed')
        self.assertTrue(user.check_password('newpassword123'))

        self.reg.refresh_from_db()
        self.assertEqual(self.reg.name, 'Student Renamed')

        # Test leave password blank -> password stays unchanged
        response = self.client.post(reverse('user_profile_edit'), {
            'name': 'Student Renamed Again',
            'username': '9876543210_updated',
            'mobile': '9876543210',
            'whatsapp': '9876543210',
            'password': '',
            'confirm_password': '',
        })
        self.assertRedirects(response, reverse('user_profile_edit'))

        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Student Renamed Again')
        self.assertTrue(user.check_password('newpassword123'))

    def test_user_profile_edit_for_admin_and_mentor(self):
        # Admin logs in
        self.client.login(username='admin_test', password='password123')

        response = self.client.get(reverse('user_profile_edit'))
        self.assertEqual(response.status_code, 200)

        # Admin edits details
        response = self.client.post(reverse('user_profile_edit'), {
            'name': 'Super Admin Updated',
            'username': 'admin_updated',
            'mobile': '1234567890',
            'password': 'newadminpass123',
            'confirm_password': 'newadminpass123',
        })
        self.assertRedirects(response, reverse('user_profile_edit'))

        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.username, 'admin_updated')
        self.assertEqual(self.admin_user.first_name, 'Super Admin Updated')
        self.assertTrue(self.admin_user.check_password('newadminpass123'))

    def test_csrf_failure_view(self):
        from registration.views import csrf_failure_view
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.post('/accounts/login/')
        response = csrf_failure_view(request, reason="CSRF token missing.")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "സുരക്ഷാ പരിശോധന പരാജയപ്പെട്ടു", status_code=403)
        self.assertContains(response, "ലോഗിൻ വീണ്ടും ശ്രമിക്കുക", status_code=403)
