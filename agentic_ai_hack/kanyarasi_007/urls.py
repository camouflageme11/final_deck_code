"""
URL configuration for kanyarasi_007 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path
from agenticai import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home_page, name="home_page"),
    path("listener/", views.listener, name="listener"),
    path("judge/", views.judge, name="judge"),
    path("scanner/", views.scanner, name="scanner"),
    path("artist/", views.artist, name="artist"),
    path("telescope/", views.telescope, name="telescope"),
    path("guide/", views.guide, name="guide"),
    path("messenger/", views.messenger, name="messenger"),
    path('mood-data/', views.mood_data, name='mood_data'),
    path('analyze-image/', views.analyze_image_labels, name='analyze_image_labels'),
    path("route_traffic/", views.route_traffic, name="route_traffic"),
    path("translate_text/", views.translate_text, name="translate_text")
]
