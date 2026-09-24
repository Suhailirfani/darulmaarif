from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from .models import Registration, CourseClass, StudentProgress, UserProfile, AppSetting
from .forms import RegistrationForm, PaymentCompletionForm
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.conf import settings
import csv
from datetime import datetime
from django.utils import timezone
import openpyxl
from django.db.models import Q

def redirect_to_referer_or_dashboard(request):
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('admin_dashboard')

def landing_view(request):
    reg_setting, _ = AppSetting.objects.get_or_create(key='registration_locked', defaults={'value_bool': False})
    is_locked = reg_setting.value_bool
    return render(request, 'registration/landing.html', {'is_locked': is_locked})

@never_cache
@ensure_csrf_cookie
def register_view(request):
    is_locked = AppSetting.objects.filter(key='registration_locked', value_bool=True).exists()
    if is_locked:
        return redirect('landing')
        
    if request.method == 'POST':
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            is_paid_val = form.cleaned_data.get('is_paid')
            if is_paid_val:
                registration = form.save(commit=False)
                registration.is_paid = False # Force to False so admin has to verify screenshot
                registration.save()
                return redirect('register_success', pk=registration.pk)
            else:
                data = {
                    'name': form.cleaned_data.get('name'),
                    'house_name': form.cleaned_data.get('house_name'),
                    'place': form.cleaned_data.get('place'),
                    'post': form.cleaned_data.get('post'),
                    'pin_code': form.cleaned_data.get('pin_code'),
                    'district': form.cleaned_data.get('district'),
                    'mobile': form.cleaned_data.get('mobile'),
                    'whatsapp': form.cleaned_data.get('whatsapp'),
                }
                request.session['temp_registration'] = data
                return redirect('complete_payment')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

@never_cache
@ensure_csrf_cookie
def complete_payment_view(request):
    is_locked = AppSetting.objects.filter(key='registration_locked', value_bool=True).exists()
    if is_locked:
        return redirect('landing')

    temp_data = request.session.get('temp_registration')
    if not temp_data:
        return redirect('register')

    if request.method == 'POST':
        form = PaymentCompletionForm(request.POST, request.FILES)
        if form.is_valid():
            mobile = temp_data.get('mobile')
            if Registration.objects.filter(mobile=mobile).exists():
                messages.error(request, "ഈ ഫോൺ നമ്പർ ഇതിനകം രജിസ്റ്റർ ചെയ്തതാണ്. (This phone number is already registered.)")
                return redirect('register')

            registration = Registration(
                name=temp_data['name'],
                house_name=temp_data['house_name'],
                place=temp_data['place'],
                post=temp_data['post'],
                pin_code=temp_data.get('pin_code', ''),
                district=temp_data['district'],
                mobile=temp_data['mobile'],
                whatsapp=temp_data['whatsapp'],
                is_paid=False,  # Needs admin verification
                transaction_time_and_date=form.cleaned_data['transaction_time_and_date'],
                transaction_id=form.cleaned_data['transaction_id'],
                screenshot=request.FILES['screenshot']
            )
            registration.save()
            
            del request.session['temp_registration']
            
            return redirect('register_success', pk=registration.pk)
    else:
        form = PaymentCompletionForm()

    return render(request, 'registration/complete_payment.html', {
        'form': form,
        'temp_data': temp_data
    })

def register_success(request, pk):
    reg = get_object_or_404(Registration, pk=pk)
    return render(request, 'registration/success.html', {'reg': reg})

def get_or_create_user_profile(user):
    """
    Safely retrieves the UserProfile for the given user, or creates one if missing.
    Links the profile to matching Registration if available, resolving any 1-to-1 conflicts.
    """
    if not user.is_authenticated:
        return None
    try:
        profile = user.profile
    except (UserProfile.DoesNotExist, AttributeError):
        if user.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'ADMIN'})
            return profile
        else:
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': 'STUDENT'}
            )

    # If this is a student profile, ensure it is linked to the matching Registration (if any)
    if profile and profile.role == 'STUDENT' and not profile.registration:
        reg = Registration.objects.filter(mobile=user.username).first()
        if reg:
            # Check if another UserProfile currently holds this registration
            UserProfile.objects.filter(registration=reg).exclude(pk=profile.pk).update(registration=None)
            profile.registration = reg
            profile.save()

    return profile

@login_required
def dashboard_router(request):
    profile = get_or_create_user_profile(request.user)
    if profile:
        if profile.role == 'ADMIN' or request.user.is_superuser:
            return redirect('admin_dashboard')
        elif profile.role == 'MENTOR':
            return redirect('mentor_dashboard')
        else:
            return redirect('student_dashboard')
    
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return redirect('student_dashboard')

@login_required
def admin_dashboard_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    all_regs = Registration.objects.all()
    total_registered = all_regs.count()
    total_paid = all_regs.filter(is_paid=True).count()
    
    pending_regs = all_regs.filter(is_paid=False).filter(Q(screenshot='') | Q(screenshot__isnull=True))
    total_pending = pending_regs.count()
    
    registrations = all_regs.exclude(id__in=pending_regs).order_by('application_num')
    
    mentors = UserProfile.objects.filter(role='MENTOR')
    course_classes = CourseClass.objects.all().order_by('order')
    students = UserProfile.objects.filter(role='STUDENT')
    
    reg_setting, _ = AppSetting.objects.get_or_create(key='registration_locked', defaults={'value_bool': False})
    is_locked = reg_setting.value_bool
    
    context = {
        'registrations': registrations,
        'total_registered': total_registered,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'mentors': mentors,
        'course_classes': course_classes,
        'students': students,
        'is_locked': is_locked,
    }
    return render(request, 'registration/dashboard.html', context)

@login_required
def admin_pending_payments_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    registrations = Registration.objects.filter(is_paid=False).filter(Q(screenshot='') | Q(screenshot__isnull=True)).order_by('application_num')
    mentors = UserProfile.objects.filter(role='MENTOR')
    
    context = {
        'registrations': registrations,
        'mentors': mentors,
    }
    return render(request, 'registration/pending_payments.html', context)

@login_required
def admin_toggle_lock_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        is_locked_val = request.POST.get('is_locked') == 'on'
        AppSetting.objects.update_or_create(key='registration_locked', defaults={'value_bool': is_locked_val})
        
    return redirect('admin_dashboard')


def parse_datetime_input(post_data):
    if not post_data:
        return None
    
    # 1. Check if separate date and 12-hour AM/PM fields are provided (from Request POST dict)
    if hasattr(post_data, 'get'):
        date_str = post_data.get('publish_date', '').strip()
        if date_str:
            try:
                hour_str = post_data.get('publish_hour', '').strip()
                minute_str = post_data.get('publish_minute', '00').strip()
                ampm_str = post_data.get('publish_ampm', 'AM').strip().upper()
                
                if hour_str:
                    hour = int(hour_str) % 12
                    if ampm_str == 'PM':
                        hour += 12
                    minute = int(minute_str) if minute_str else 0
                else:
                    hour = 0
                    minute = 0
                    
                dt = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=hour, minute=minute)
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt)
                return dt
            except (ValueError, TypeError):
                pass

        raw_val = post_data.get('publish_at', '').strip()
    else:
        raw_val = str(post_data).strip()

    # 2. Fallback to raw string parsing (ISO or 12/24-hr formats)
    if raw_val:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(raw_val, fmt)
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt)
                return dt
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(raw_val)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt)
            return dt
        except (ValueError, TypeError):
            pass

    return None

@login_required
def admin_manage_class_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            raw_vid = request.POST.get('youtube_video_id', '').strip()
            
            # Safely extract YouTube ID if user pasted full URL
            import re
            vid_id = raw_vid
            
            # Match standard youtube.com/watch?v=ID or youtu.be/ID
            match = re.search(r'(?:v=|youtu\.be/|embed/)([^&?/\s]{11})', raw_vid)
            if match:
                vid_id = match.group(1)
            elif len(raw_vid) == 11:
                vid_id = raw_vid
            else:
                # Fallback, just try to take the last 11 characters if it's a weird url, or just save as is
                vid_id = raw_vid[-11:] if len(raw_vid) > 11 else raw_vid
                
            publish_at = parse_datetime_input(request.POST)
            CourseClass.objects.create(
                title=request.POST.get('title'),
                youtube_video_id=vid_id,
                order=request.POST.get('order'),
                description=request.POST.get('description', ''),
                publish_at=publish_at
            )
        elif action == 'edit':
            class_id = request.POST.get('class_id')
            raw_vid = request.POST.get('youtube_video_id', '').strip()
            
            import re
            vid_id = raw_vid
            match = re.search(r'(?:v=|youtu\.be/|embed/)([^&?/\s]{11})', raw_vid)
            if match:
                vid_id = match.group(1)
            elif len(raw_vid) == 11:
                vid_id = raw_vid
            else:
                vid_id = raw_vid[-11:] if len(raw_vid) > 11 else raw_vid
                
            publish_at = parse_datetime_input(request.POST)
            CourseClass.objects.filter(id=class_id).update(
                title=request.POST.get('title'),
                youtube_video_id=vid_id,
                order=request.POST.get('order'),
                description=request.POST.get('description', ''),
                publish_at=publish_at
            )
        elif action == 'delete':
            class_id = request.POST.get('class_id')
            CourseClass.objects.filter(id=class_id).delete()
            
    return redirect('admin_dashboard')

@login_required
def admin_manage_mentor_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        name = request.POST.get('name')
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        
        if not User.objects.filter(username=mobile).exists():
            user = User.objects.create_user(username=mobile, password=password, first_name=name)
            UserProfile.objects.create(user=user, role='MENTOR')
            
    return redirect('admin_dashboard')

@login_required
def admin_assign_students_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        student_ids = request.POST.getlist('student_ids') # These are now Registration IDs
        
        if not student_ids:
            return redirect_to_referer_or_dashboard(request)
            
        if action == 'assign':
            mentor_id = request.POST.get('mentor_id')
            if mentor_id:
                mentor_profile = get_object_or_404(UserProfile, id=mentor_id, role='MENTOR')
                UserProfile.objects.filter(registration__id__in=student_ids, role='STUDENT').update(mentor=mentor_profile)
        
        elif action == 'delete':
            # Bulk delete
            # Delete associated User accounts first (cascades to UserProfile)
            users_to_delete = User.objects.filter(profile__registration__id__in=student_ids)
            users_to_delete.delete()
            # Delete registrations
            for reg in Registration.objects.filter(id__in=student_ids):
                if reg.screenshot and os.path.isfile(reg.screenshot.path):
                    os.remove(reg.screenshot.path)
                reg.delete()
                
    return redirect_to_referer_or_dashboard(request)

import os

@login_required
def admin_verify_payment_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        reg_id = request.POST.get('reg_id')
        reg = get_object_or_404(Registration, id=reg_id)
        if not reg.is_paid:
            reg.is_paid = True
            reg.save() # This triggers post_save to create the User account
            
            # Delete the screenshot to reduce storage
            if reg.screenshot:
                if os.path.isfile(reg.screenshot.path):
                    os.remove(reg.screenshot.path)
                reg.screenshot = None
                reg.save()
                
    return redirect_to_referer_or_dashboard(request)

def service_worker_view(request):
    sw_code = """
const CACHE_NAME = 'al-mara-cache-v2';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }

    const url = new URL(event.request.url);
    if (url.pathname.startsWith('/accounts/') || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/dashboard/')) {
        return;
    }

    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
"""
    return HttpResponse(sw_code.strip(), content_type='application/javascript')



@login_required
def admin_edit_registration_view(request):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
        
    if request.method == 'POST':
        reg_id = request.POST.get('reg_id')
        reg = get_object_or_404(Registration, id=reg_id)
        
        old_mobile = reg.mobile
        new_mobile = request.POST.get('mobile', reg.mobile).strip()
        
        if old_mobile != new_mobile and Registration.objects.filter(mobile=new_mobile).exclude(id=reg.id).exists():
            messages.error(request, f"കഴിയുന്നില്ല: {new_mobile} എന്ന ഫോൺ നമ്പർ ഇതിനകം മറ്റൊരു അപേക്ഷകൻ രജിസ്റ്റർ ചെയ്തിട്ടുണ്ട്. (Cannot update: The mobile number {new_mobile} is already registered by another applicant.)")
            return redirect_to_referer_or_dashboard(request)
            
        reg.name = request.POST.get('name', reg.name).strip()
        reg.house_name = request.POST.get('house_name', reg.house_name).strip()
        reg.place = request.POST.get('place', reg.place).strip()
        reg.post = request.POST.get('post', reg.post).strip()
        reg.pin_code = request.POST.get('pin_code', reg.pin_code).strip()
        reg.district = request.POST.get('district', reg.district).strip()
        reg.mobile = new_mobile
        reg.whatsapp = request.POST.get('whatsapp', reg.whatsapp).strip()
        
        reg.save()
        messages.success(request, f"അപേക്ഷകന്റെ വിവരങ്ങൾ വിജയകരമായി പുതുക്കി. (Details of {reg.name} updated successfully.)")
                
    return redirect_to_referer_or_dashboard(request)

@login_required
def admin_print_registration_view(request, pk):
    if not request.user.is_superuser and getattr(request.user, 'profile', None) and request.user.profile.role != 'ADMIN':
        return redirect('landing')
    reg = get_object_or_404(Registration, pk=pk)
    return render(request, 'registration/print_registration.html', {'reg': reg})

@login_required
def export_excel_view(request):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=registrations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Registrations'
    
    columns = [
        'ID', 'Name', 'House Name', 'Place', 'Post', 'PIN Code', 'District',
        'Mobile', 'WhatsApp', 'Paid', 'Transaction Time', 'Transaction ID', 'Created At'
    ]
    row_num = 1
    
    for col_num, column_title in enumerate(columns, 1):
        cell = worksheet.cell(row=row_num, column=col_num)
        cell.value = column_title
        
    for reg in Registration.objects.all().order_by('-created_at'):
        row_num += 1
        row = [
            f"APP-{reg.application_number}", reg.name, reg.house_name, reg.place, reg.post, reg.pin_code, reg.district,
            reg.mobile, reg.whatsapp, 'Yes' if reg.is_paid else 'No',
            reg.transaction_time_and_date.strftime('%Y-%m-%d %H:%M:%S') if reg.transaction_time_and_date else '',
            reg.transaction_id,
            reg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ]
        for col_num, cell_value in enumerate(row, 1):
            cell = worksheet.cell(row=row_num, column=col_num)
            cell.value = cell_value
            
    workbook.save(response)
    return response

@login_required
def student_dashboard_view(request):
    profile = get_or_create_user_profile(request.user)
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    if not is_admin and profile and profile.role == 'MENTOR':
        return redirect('mentor_dashboard')
        
    now = timezone.now()
    if is_admin:
        classes = CourseClass.objects.all().order_by('order')
    else:
        classes = CourseClass.objects.filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now)).order_by('order')
        
    progress_list = StudentProgress.objects.filter(student=request.user)
    
    completed_class_ids = set(p.course_class.id for p in progress_list if p.is_completed)
    
    class_data = []
    is_unlocked = True
    
    for c in classes:
        completed = c.id in completed_class_ids
        class_data.append({
            'class': c,
            'is_unlocked': True if is_admin else is_unlocked,
            'is_completed': completed
        })
        is_unlocked = completed
        
    return render(request, 'registration/student_dashboard.html', {
        'class_data': class_data,
        'is_admin_preview': is_admin
    })

@login_required
def classroom_view(request, class_id):
    profile = get_or_create_user_profile(request.user)
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    if not is_admin and profile and profile.role == 'MENTOR':
        return redirect('mentor_dashboard')
        
    course_class = get_object_or_404(CourseClass, id=class_id)
    
    # Check if scheduled for future release (only enforce for standard students)
    if not is_admin and course_class.publish_at and timezone.now() < course_class.publish_at:
        messages.warning(request, "ഈ ക്ലാസ് നിശ്ചയിച്ച തീയതിയിലും സമയത്തിലും മാത്രമേ ലഭ്യമാകൂ. (This class is scheduled for a future date and time.)")
        return redirect('student_dashboard')
    
    # Check if unlocked (only enforce for standard students)
    if not is_admin and course_class.order > 1:
        prev_class = CourseClass.objects.filter(order=course_class.order - 1).first()
        if prev_class:
            prev_progress = StudentProgress.objects.filter(student=request.user, course_class=prev_class, is_completed=True).exists()
            if not prev_progress:
                return HttpResponse("Please watch the previous class first.", status=403)
                
    is_already_completed = StudentProgress.objects.filter(student=request.user, course_class=course_class, is_completed=True).exists()
                
    if request.method == 'POST' and not is_already_completed:
        progress, created = StudentProgress.objects.get_or_create(student=request.user, course_class=course_class)
        progress.is_completed = True
        progress.save()
        return redirect('student_dashboard')
        
    return render(request, 'registration/classroom.html', {
        'course_class': course_class, 
        'is_already_completed': is_already_completed,
        'is_admin_preview': is_admin
    })

@login_required
def mentor_dashboard_view(request):
    if getattr(request.user, 'profile', None) and request.user.profile.role != 'MENTOR':
        return redirect('landing')
        
    total_classes = CourseClass.objects.count()
    student_data = []
    
    try:
        profile = request.user.profile
        assigned_students = profile.mentees.all()
        
        for student_profile in assigned_students:
            user = student_profile.user
            completed_count = StudentProgress.objects.filter(student=user, is_completed=True).count()
            last_progress = StudentProgress.objects.filter(student=user, is_completed=True).order_by('-completed_at').first()
            
            student_data.append({
                'name': user.first_name,
                'mobile': user.username,
                'completed_count': completed_count,
                'total_classes': total_classes,
                'last_activity': last_progress.completed_at if last_progress else None
            })
    except:
        pass
        
    return render(request, 'registration/mentor_dashboard.html', {'student_data': student_data})


@never_cache
@ensure_csrf_cookie
def edit_my_registration_view(request):
    action = request.GET.get('action')
    if action == 'clear':
        if 'editable_reg_id' in request.session:
            del request.session['editable_reg_id']
        return redirect('edit_my_registration')

    editable_reg_id = request.session.get('editable_reg_id')
    reg = None
    if editable_reg_id:
        reg = get_object_or_404(Registration, id=editable_reg_id)

    if request.method == 'POST':
        # If user is in lookup mode
        if not reg:
            mobile = request.POST.get('mobile', '').strip()
            whatsapp = request.POST.get('whatsapp', '').strip()
            app_num_str = request.POST.get('app_num', '').strip()

            if not mobile:
                messages.error(request, "മൊബൈൽ നമ്പർ നൽകേണ്ടതുണ്ട്. (Mobile number is required.)")
                return render(request, 'registration/edit_my_registration.html', {'reg': None})

            # Find applicant matching mobile
            try:
                candidate = Registration.objects.get(mobile=mobile)
                # Verify match
                is_match = False
                
                # Check WhatsApp match if provided
                if whatsapp and candidate.whatsapp == whatsapp:
                    is_match = True
                # Check Application Number match if provided
                elif app_num_str:
                    # Clean up string app number, remove 'APP-' if entered
                    clean_app_num = app_num_str.upper().replace('APP-', '').strip()
                    try:
                        app_num_int = int(clean_app_num)
                        if candidate.application_num == app_num_int:
                            is_match = True
                    except ValueError:
                        pass
                
                if is_match:
                    request.session['editable_reg_id'] = candidate.id
                    messages.success(request, f"രജിസ്ട്രേഷൻ കണ്ടെത്തി: {candidate.name}. നിങ്ങൾക്ക് ഇപ്പോൾ വിവരങ്ങൾ തിരുത്താം. (Registration found: {candidate.name}. You can edit your details now.)")
                    return redirect('edit_my_registration')
                else:
                    messages.error(request, "നൽകിയ വിവരങ്ങൾ പൊരുത്തപ്പെടുന്നില്ല. ദയവായി ശരിയായ വിവരങ്ങൾ നൽകുക. (The details provided do not match. Please enter correct details.)")
            except Registration.DoesNotExist:
                messages.error(request, "ഈ മൊബൈൽ നമ്പറിൽ രജിസ്ട്രേഷൻ ഒന്നും കണ്ടെത്തിയില്ല. (No registration found for this mobile number.)")
            
            return render(request, 'registration/edit_my_registration.html', {'reg': None})
            
        else:
            # User is submitting edits
            name = request.POST.get('name', '').strip()
            house_name = request.POST.get('house_name', '').strip()
            place = request.POST.get('place', '').strip()
            post = request.POST.get('post', '').strip()
            pin_code = request.POST.get('pin_code', '').strip()
            district = request.POST.get('district', '').strip()
            whatsapp = request.POST.get('whatsapp', '').strip()

            if not (name and house_name and place and post and pin_code and district and whatsapp):
                messages.error(request, "ദയവായി എല്ലാ വിവരങ്ങളും പൂരിപ്പിക്കുക. പിൻകോഡ് നിർബന്ധമാണ്. (Please fill in all details. PIN Code is compulsory.)")
                return render(request, 'registration/edit_my_registration.html', {'reg': reg})

            reg.name = name
            reg.house_name = house_name
            reg.place = place
            reg.post = post
            reg.pin_code = pin_code
            reg.district = district
            reg.whatsapp = whatsapp
            reg.save()

            messages.success(request, "നിങ്ങളുടെ വിവരങ്ങൾ വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തിരിക്കുന്നു! (Your details have been successfully updated!)")
            del request.session['editable_reg_id']
            return redirect('register_success', pk=reg.pk)

    return render(request, 'registration/edit_my_registration.html', {'reg': reg})


@login_required
def user_profile_edit_view(request):
    profile = get_or_create_user_profile(request.user)
    reg = getattr(profile, 'registration', None) if profile else None
    if not reg:
        reg = Registration.objects.filter(mobile=request.user.username).first()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        username = request.POST.get('username', '').strip()
        mobile = request.POST.get('mobile', '').strip()
        whatsapp = request.POST.get('whatsapp', '').strip()
        new_password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        errors = []

        if not name:
            errors.append("പേര് നൽകേണ്ടതുണ്ട്. (Name is required.)")

        if not username:
            errors.append("യൂസർനെയിം നൽകേണ്ടതുണ്ട്. (Username is required.)")
        elif User.objects.filter(username=username).exclude(pk=request.user.pk).exists():
            errors.append(f"'{username}' എന്ന യൂസർനെയിം ഇതിനകം മറ്റൊരു അക്കൗണ്ടിൽ നിലവിലുണ്ട്. (This username is already taken.)")

        if reg and mobile:
            if Registration.objects.filter(mobile=mobile).exclude(pk=reg.pk).exists():
                errors.append(f"'{mobile}' എന്ന മൊബൈൽ നമ്പർ ഇതിനകം മറ്റൊരു അപേക്ഷകൻ രജിസ്റ്റർ ചെയ്തിട്ടുണ്ട്. (Mobile number is already registered by another applicant.)")

        if new_password:
            if len(new_password) < 4:
                errors.append("പാസ്‌വേഡിൽ കുറഞ്ഞത് 4 അക്ഷരങ്ങൾ/അക്കങ്ങൾ ഉണ്ടായിരിക്കണം. (Password must be at least 4 characters long.)")
            elif new_password != confirm_password:
                errors.append("നൽകിയ പാസ്‌വേഡുകൾ പരസ്പരം പൊരുത്തപ്പെടുന്നില്ല. (Passwords do not match.)")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            # Update user details
            user = request.user
            user.first_name = name
            user.username = username
            if new_password:
                user.set_password(new_password)
            user.save()

            if new_password:
                update_session_auth_hash(request, user)

            # Update registration details if linked
            if reg:
                reg.name = name
                if mobile:
                    reg.mobile = mobile
                if whatsapp:
                    reg.whatsapp = whatsapp
                reg._skip_username_sync = True
                reg.save()

            messages.success(request, "നിങ്ങളുടെ പ്രൊഫൈൽ വിവരങ്ങൾ വിജയകരമായി പുതുക്കി! (Profile updated successfully!)")
            return redirect('user_profile_edit')

    return render(request, 'registration/profile_edit.html', {
        'profile': profile,
        'reg': reg,
    })


def csrf_failure_view(request, reason=""):
    return render(request, 'registration/csrf_failure.html', {
        'reason': reason,
        'debug': getattr(settings, 'DEBUG', False),
    }, status=403)


@login_required
def attendance_list_view(request):
    profile = get_or_create_user_profile(request.user)
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    is_mentor = profile and profile.role == 'MENTOR'

    if not is_admin and not is_mentor:
        return redirect('student_dashboard')

    now = timezone.now()
    all_classes = list(CourseClass.objects.all().order_by('order'))
    live_classes = [c for c in all_classes if not c.publish_at or c.publish_at <= now]
    scheduled_classes = [c for c in all_classes if c.publish_at and c.publish_at > now]

    total_live_classes = len(live_classes)
    total_all_classes = len(all_classes)

    # Last 5 live classes for table cells
    recent_classes = live_classes[-5:] if total_live_classes > 5 else live_classes

    mentor_filter = request.GET.get('mentor', '').strip()
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    regs_query = Registration.objects.filter(is_paid=True).select_related(
        'student_profile__mentor__user', 
        'student_profile__user'
    ).order_by('application_num')

    if is_mentor and not is_admin:
        regs_query = regs_query.filter(student_profile__mentor=profile)
    elif mentor_filter:
        if mentor_filter == 'unassigned':
            regs_query = regs_query.filter(student_profile__mentor__isnull=True)
        else:
            try:
                regs_query = regs_query.filter(student_profile__mentor_id=int(mentor_filter))
            except ValueError:
                pass

    if search_query:
        clean_app_num = search_query.upper().replace('APP-', '').strip()
        q_obj = (
            Q(name__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(whatsapp__icontains=search_query) |
            Q(place__icontains=search_query) |
            Q(district__icontains=search_query)
        )
        if clean_app_num.isdigit():
            q_obj |= Q(application_num=int(clean_app_num))
        regs_query = regs_query.filter(q_obj)

    student_users_map = {}
    for reg in regs_query:
        user = None
        if hasattr(reg, 'student_profile') and reg.student_profile and reg.student_profile.user:
            user = reg.student_profile.user
        else:
            user = User.objects.filter(username=reg.mobile).first()
            if not user and reg.is_paid:
                user = User.objects.create_user(
                    username=reg.mobile,
                    password=f"APP-{reg.application_number}",
                    first_name=reg.name
                )
            if user:
                reg_profile = get_or_create_user_profile(user)
                if reg_profile and reg_profile.registration != reg:
                    reg_profile.registration = reg
                    reg_profile.save()
        if user:
            student_users_map[reg.id] = user

    user_ids = [u.id for u in student_users_map.values() if u]
    progress_qs = StudentProgress.objects.filter(
        student_id__in=user_ids, 
        is_completed=True
    ).values('student_id', 'course_class_id', 'completed_at')

    progress_map = {}
    for p in progress_qs:
        progress_map[(p['student_id'], p['course_class_id'])] = p['completed_at']

    students_attendance_data = []
    students_json_list = []
    total_attended_all_students = 0
    full_completed_count = 0
    zero_attended_count = 0

    live_class_ids = set(c.id for c in live_classes)
    recent_class_ids = set(c.id for c in recent_classes)

    for reg in regs_query:
        user = student_users_map.get(reg.id)
        user_id = user.id if user else None

        all_classes_status = []
        recent_classes_status = []
        json_classes_status = []
        attended_live_count = 0

        for c in all_classes:
            is_live = c.id in live_class_ids
            completed_at = progress_map.get((user_id, c.id)) if user_id else None
            is_attended = completed_at is not None
            if is_attended and is_live:
                attended_live_count += 1

            completed_at_str = timezone.localtime(completed_at).strftime("%b %d, %Y %I:%M %p") if completed_at else None

            c_info = {
                'class_id': c.id,
                'order': c.order,
                'title': c.title,
                'is_live': is_live,
                'publish_at': c.publish_at,
                'is_attended': is_attended,
                'completed_at': completed_at,
                'completed_at_str': completed_at_str,
            }
            all_classes_status.append(c_info)
            if c.id in recent_class_ids:
                recent_classes_status.append(c_info)

            json_classes_status.append({
                'class_id': c.id,
                'order': c.order,
                'title': c.title,
                'is_live': is_live,
                'is_attended': is_attended,
                'completed_at_str': completed_at_str,
            })

        percentage = round((attended_live_count / total_live_classes * 100), 1) if total_live_classes > 0 else 0
        if attended_live_count == total_live_classes and total_live_classes > 0:
            full_completed_count += 1
        elif attended_live_count == 0:
            zero_attended_count += 1

        total_attended_all_students += attended_live_count

        mentor_name = "-"
        mentor_id = None
        if hasattr(reg, 'student_profile') and reg.student_profile and reg.student_profile.mentor:
            mentor_profile = reg.student_profile.mentor
            mentor_id = mentor_profile.id
            mentor_user = mentor_profile.user
            mentor_name = mentor_user.first_name or mentor_user.username

        # Filter by status based on live classes
        if status_filter == 'completed' and (attended_live_count != total_live_classes or total_live_classes == 0):
            continue
        elif status_filter == 'in_progress' and (attended_live_count == 0 or attended_live_count == total_live_classes):
            continue
        elif status_filter == 'not_started' and attended_live_count > 0:
            continue

        students_attendance_data.append({
            'registration': reg,
            'reg_id': reg.id,
            'app_number': f"APP-{reg.application_number}",
            'name': reg.name,
            'mobile': reg.mobile,
            'whatsapp': reg.whatsapp,
            'place': reg.place,
            'district': reg.district,
            'mentor_id': mentor_id,
            'mentor_name': mentor_name,
            'user_id': user_id,
            'recent_classes_status': recent_classes_status,
            'all_classes_status': all_classes_status,
            'attended_count': attended_live_count,
            'total_classes': total_live_classes,
            'total_all_classes': total_all_classes,
            'percentage': percentage,
        })

        students_json_list.append({
            'reg_id': reg.id,
            'app_number': f"APP-{reg.application_number}",
            'name': reg.name,
            'mobile': reg.mobile,
            'whatsapp': reg.whatsapp,
            'place': reg.place,
            'district': reg.district,
            'mentor_id': mentor_id,
            'mentor_name': mentor_name,
            'user_id': user_id,
            'all_classes_status': json_classes_status,
            'attended_count': attended_live_count,
            'total_classes': total_live_classes,
            'percentage': percentage,
        })

    total_students_count = len(students_attendance_data)
    avg_attendance_rate = round((total_attended_all_students / (total_students_count * total_live_classes) * 100), 1) if (total_students_count > 0 and total_live_classes > 0) else 0

    mentors = UserProfile.objects.filter(role='MENTOR').select_related('user').order_by('user__first_name')

    context = {
        'recent_classes': recent_classes,
        'all_classes': all_classes,
        'live_classes': live_classes,
        'scheduled_classes': scheduled_classes,
        'students_data': students_attendance_data,
        'students_json_list': students_json_list,
        'total_live_classes': total_live_classes,
        'total_all_classes': total_all_classes,
        'total_students_count': total_students_count,
        'full_completed_count': full_completed_count,
        'zero_attended_count': zero_attended_count,
        'avg_attendance_rate': avg_attendance_rate,
        'mentors': mentors,
        'selected_mentor': mentor_filter,
        'search_query': search_query,
        'status_filter': status_filter,
        'is_admin': is_admin,
        'is_mentor': is_mentor,
    }
    return render(request, 'registration/attendance_list.html', context)


@login_required
def admin_toggle_student_attendance_view(request):
    profile = get_or_create_user_profile(request.user)
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    is_mentor = profile and profile.role == 'MENTOR'

    if not is_admin and not is_mentor:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        reg_id = request.POST.get('reg_id')
        class_id = request.POST.get('class_id')

        course_class = get_object_or_404(CourseClass, id=class_id)

        user = None
        if user_id:
            user = get_object_or_404(User, id=user_id)
        elif reg_id:
            reg = get_object_or_404(Registration, id=reg_id)
            user = User.objects.filter(username=reg.mobile).first()
            if not user:
                user = User.objects.create_user(
                    username=reg.mobile, 
                    password=f"APP-{reg.application_number}", 
                    first_name=reg.name
                )
                UserProfile.objects.get_or_create(user=user, defaults={'role': 'STUDENT', 'registration': reg})

        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        # If mentor, check assignment
        if is_mentor and not is_admin:
            student_profile = getattr(user, 'profile', None)
            if not student_profile or student_profile.mentor != profile:
                return JsonResponse({'error': 'Permission denied: Student not assigned to you'}, status=403)

        progress = StudentProgress.objects.filter(student=user, course_class=course_class).first()
        if progress and progress.is_completed:
            progress.is_completed = False
            progress.save()
            new_state = False
            completed_str = None
        else:
            if not progress:
                progress = StudentProgress(student=user, course_class=course_class, is_completed=True)
            else:
                progress.is_completed = True
            progress.save()
            new_state = True
            completed_str = timezone.localtime(progress.completed_at).strftime("%b %d, %Y %I:%M %p")

        now = timezone.now()
        live_classes = CourseClass.objects.filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))
        total_live_classes = live_classes.count()
        attended_count = StudentProgress.objects.filter(student=user, course_class__in=live_classes, is_completed=True).count()
        percentage = round((attended_count / total_live_classes * 100), 1) if total_live_classes > 0 else 0

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1':
            return JsonResponse({
                'success': True,
                'is_attended': new_state,
                'completed_at_str': completed_str,
                'attended_count': attended_count,
                'total_classes': total_live_classes,
                'percentage': percentage,
            })

        messages.success(request, f"Attendance updated for {user.first_name or user.username} - Class {course_class.order}.")
        return redirect_to_referer_or_dashboard(request)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def export_attendance_excel_view(request):
    import openpyxl
    import openpyxl.styles
    import openpyxl.utils

    profile = get_or_create_user_profile(request.user)
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    is_mentor = profile and profile.role == 'MENTOR'

    if not is_admin and not is_mentor:
        return redirect('student_dashboard')

    now = timezone.now()
    live_classes = list(CourseClass.objects.filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now)).order_by('order'))
    total_live_classes = len(live_classes)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=attendance_live_classes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Live Class Attendance'

    columns = ['App No', 'Student Name', 'Mobile', 'WhatsApp', 'District', 'Mentor']
    for c in live_classes:
        columns.append(f"Class {c.order}")
    columns.extend(['Total Attended', 'Total Live Classes', 'Attendance %'])

    header_fill = openpyxl.styles.PatternFill(start_color="4D0B5A", end_color="4D0B5A", fill_type="solid")
    header_font = openpyxl.styles.Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = openpyxl.styles.Alignment(horizontal="center", vertical="center")
    align_left = openpyxl.styles.Alignment(horizontal="left", vertical="center")

    for col_num, col_title in enumerate(columns, 1):
        cell = worksheet.cell(row=1, column=col_num)
        cell.value = col_title
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    regs_query = Registration.objects.filter(is_paid=True).select_related(
        'student_profile__mentor__user', 
        'student_profile__user'
    ).order_by('application_num')

    if is_mentor and not is_admin:
        regs_query = regs_query.filter(student_profile__mentor=profile)

    user_ids = []
    user_map = {}
    for reg in regs_query:
        user = None
        if hasattr(reg, 'student_profile') and reg.student_profile and reg.student_profile.user:
            user = reg.student_profile.user
        else:
            user = User.objects.filter(username=reg.mobile).first()
        if user:
            user_map[reg.id] = user
            user_ids.append(user.id)

    progress_qs = StudentProgress.objects.filter(
        student_id__in=user_ids, 
        is_completed=True
    ).values('student_id', 'course_class_id', 'completed_at')

    progress_map = {(p['student_id'], p['course_class_id']): p['completed_at'] for p in progress_qs}

    row_num = 1
    for reg in regs_query:
        row_num += 1
        user = user_map.get(reg.id)
        user_id = user.id if user else None

        mentor_name = "-"
        if hasattr(reg, 'student_profile') and reg.student_profile and reg.student_profile.mentor:
            mentor_user = reg.student_profile.mentor.user
            mentor_name = mentor_user.first_name or mentor_user.username

        row_data = [
            f"APP-{reg.application_number}",
            reg.name,
            reg.mobile,
            reg.whatsapp,
            reg.district,
            mentor_name,
        ]

        attended_count = 0
        for c in live_classes:
            completed_at = progress_map.get((user_id, c.id)) if user_id else None
            if completed_at:
                attended_count += 1
                row_data.append("Attended")
            else:
                row_data.append("-")

        percentage = f"{round((attended_count / total_live_classes * 100), 1)}%" if total_live_classes > 0 else "0%"
        row_data.extend([attended_count, total_live_classes, percentage])

        for col_num, val in enumerate(row_data, 1):
            cell = worksheet.cell(row=row_num, column=col_num)
            cell.value = val
            if col_num in [1, 3, 4, 6] or col_num > 6:
                cell.alignment = align_center
            else:
                cell.alignment = align_left

    for col in worksheet.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)

    workbook.save(response)
    return response




