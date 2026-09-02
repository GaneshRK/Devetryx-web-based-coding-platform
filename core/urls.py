from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Pages
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('contact-submit/', views.contact_submit, name='contact_submit'),
    path('Python_compiler/', views.python_compiler, name='python_compiler'),

    # Execution Engine & AI Intelligence APIs
    path('run/python/', views.run_python_code, name='run_python'),
    path('api/ai/mentor/', views.ai_mentor_view, name='ai_mentor'),
    path('api/skills/', views.skill_graph_view, name='skill_graph'),
    path('api/events/', views.events_feed_view, name='events_feed'),
]
