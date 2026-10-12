"""Registers the tables with Django's built-in admin site (/django-admin/) so they can be browsed like a database viewer."""
from django.contrib import admin
from .models import Admin, Booking, Entrance, Level, Slot


@admin.register(Entrance)
class EntranceAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'status')

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'status')

@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('label', 'entrance', 'level', 'status', 'code', 'booked_at')
    list_filter = ('status', 'entrance', 'level')
    search_fields = ('label', 'code')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('slot_label', 'entrance_name', 'code', 'entered_at', 'exited_at', 'released_by')

@admin.register(Admin)
class AdminAccountAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'full_name', 'is_active')
    fields = ('employee_number', 'full_name', 'is_active', 'is_staff', 'is_superuser')
