from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('new/', views.new_view, name='new'),
    path('<int:conversation_id>/', views.detail_view, name='detail'),
    path('<int:conversation_id>/message/', views.send_message_view, name='send_message'),
    path('<int:conversation_id>/delete/', views.delete_view, name='delete'),
    path('<int:conversation_id>/clear/', views.clear_view, name='clear'),
]
