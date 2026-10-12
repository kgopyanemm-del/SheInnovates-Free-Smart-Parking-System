from django.urls import path
from . import views as v

urlpatterns = [
    # driver
    path('', v.home, name='home'),
    path('book/', v.book_entrance, name='book_entrance'),
    path('book/<int:eid>/', v.book_level, name='book_level'),
    path('book/<int:eid>/<int:lid>/', v.book_slots, name='book_slots'),
    path('book/slot/<int:pk>/', v.book_confirm, name='book_confirm'),
    path('receipt/', v.book_receipt, name='book_receipt'),
    path('exit/', v.exit_gate, name='exit_gate'),
    path('exit/<int:eid>/', v.exit_verify, name='exit_verify'),
    path('exit/receipt/', v.exit_receipt, name='exit_receipt'),
    # admin
    path('admin-panel/login/', v.admin_login, name='admin_login'),
    path('admin-panel/logout/', v.admin_logout, name='admin_logout'),
    path('admin-panel/', v.dashboard, name='dashboard'),
    path('admin-panel/status/', v.status, name='status'),
    path('admin-panel/status/<str:kind>/', v.status_list, name='status_list'),
    path('admin-panel/release/<int:pk>/', v.release, name='release'),
    path('admin-panel/manage/', v.manage, name='manage'),
    path('admin-panel/manage/<str:action>/', v.manage_action, name='manage_action'),
    path('admin-panel/admins/', v.admins, name='admins'),
    path('admin-panel/admins/add/', v.admin_add, name='admin_add'),
    path('admin-panel/admins/<int:pk>/remove/', v.admin_remove, name='admin_remove'),
]
