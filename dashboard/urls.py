from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('users/', views.users_view, name='users'),
    path('users/<int:user_id>/role/', views.change_user_role_view, name='change_role'),
    path('users/<int:user_id>/toggle-status/', views.toggle_user_status_view, name='toggle_status'),
    path('system/', views.system_status_view, name='system_status'),
]
