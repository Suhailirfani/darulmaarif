from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import Registration
from .forms import RegistrationForm
import csv
from datetime import datetime
import openpyxl

def landing_view(request):
    return render(request, 'registration/landing.html')

def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('register_success')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

def register_success(request):
    return render(request, 'registration/success.html')

@login_required
def dashboard_view(request):
    registrations = Registration.objects.all().order_by('-created_at')
    total_registered = registrations.count()
    total_paid = registrations.filter(is_paid=True).count()
    
    context = {
        'registrations': registrations,
        'total_registered': total_registered,
        'total_paid': total_paid,
    }
    return render(request, 'registration/dashboard.html', context)

@login_required
def export_excel_view(request):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=registrations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Registrations'
    
    columns = [
        'ID', 'Name', 'House Name', 'Place', 'Post', 'District',
        'Mobile', 'WhatsApp', 'Paid', 'Transaction Time', 'Transaction ID', 'Created At'
    ]
    row_num = 1
    
    for col_num, column_title in enumerate(columns, 1):
        cell = worksheet.cell(row=row_num, column=col_num)
        cell.value = column_title
        
    for reg in Registration.objects.all().order_by('-created_at'):
        row_num += 1
        row = [
            reg.id, reg.name, reg.house_name, reg.place, reg.post, reg.district,
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
