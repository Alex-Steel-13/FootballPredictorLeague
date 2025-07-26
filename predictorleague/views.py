from django.shortcuts import render

def home(request):
    return render(request, 'home.html')

def info(request):
    return render(request, 'info.html')