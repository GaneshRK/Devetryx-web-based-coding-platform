from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('contact-submit/', views.contact_submit, name='contact_submit'),
    path('run/python/', views.run_python_code, name='run_python'),
    path('Python_compiler/', views.python_compiler,name='python_compiler'),
]
