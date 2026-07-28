from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Registration, CourseClass, StudentProgress, UserProfile, AppSetting
from .forms import RegistrationForm, PaymentCompletionForm
import csv
from datetime import datetime
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

@login_required
def dashboard_router(request):
    try:
        profile = request.user.profile
        if profile.role == 'ADMIN':
            return redirect('admin_dashboard')
        elif profile.role == 'MENTOR':
            return redirect('mentor_dashboard')
        else:
            return redirect('student_dashboard')
    except:
        if request.user.is_superuser:
            return redirect('admin_dashboard')
        return redirect('landing')

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
                
            CourseClass.objects.create(
                title=request.POST.get('title'),
                youtube_video_id=vid_id,
                order=request.POST.get('order'),
                description=request.POST.get('description', '')
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
                
            CourseClass.objects.filter(id=class_id).update(
                title=request.POST.get('title'),
                youtube_video_id=vid_id,
                order=request.POST.get('order'),
                description=request.POST.get('description', '')
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
    return HttpResponse("// Service worker placeholder", content_type='application/javascript')

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
    if getattr(request.user, 'profile', None) and request.user.profile.role != 'STUDENT':
        return redirect('landing')
        
    classes = CourseClass.objects.all().order_by('order')
    progress_list = StudentProgress.objects.filter(student=request.user)
    
    completed_class_ids = set(p.course_class.id for p in progress_list if p.is_completed)
    
    class_data = []
    is_unlocked = True
    
    for c in classes:
        completed = c.id in completed_class_ids
        class_data.append({
            'class': c,
            'is_unlocked': is_unlocked,
            'is_completed': completed
        })
        is_unlocked = completed
        
    return render(request, 'registration/student_dashboard.html', {'class_data': class_data})

@login_required
def classroom_view(request, class_id):
    if getattr(request.user, 'profile', None) and request.user.profile.role != 'STUDENT':
        return redirect('landing')
        
    course_class = get_object_or_404(CourseClass, id=class_id)
    
    # Check if unlocked
    if course_class.order > 1:
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
        
    return render(request, 'registration/classroom.html', {'course_class': course_class, 'is_already_completed': is_already_completed})

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
