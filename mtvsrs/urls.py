"""
URL configuration for mtvsrs project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home_page, name="home"),
    path("show/<int:show_id>/", views.show_page, name='show'),
    path("register", views.register_user, name="register"),
    path("", include("django.contrib.auth.urls")),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LoginView.as_view(), name='logout'),
    path('search/', views.search_feature, name='search_view'),
    path("my_list/", views.my_list_page, name='my_list'),
    path("change_status/", views.change_status, name='change_status'),
    path("submit_review/", views.submit_review, name='submit_review'),

]
