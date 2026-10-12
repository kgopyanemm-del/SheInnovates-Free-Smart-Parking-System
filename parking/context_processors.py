from .models import MAINTENANCE, OPEN, Entrance, Level, Slot


def maintenance(request):
    """Runs on every page: lists whatever is under maintenance so the banner can show it."""
    items = [e.display_name for e in Entrance.objects.exclude(status=OPEN)] + [l.name for l in Level.objects.exclude(status=OPEN)]
    count = Slot.objects.filter(status=MAINTENANCE).count()
    if count:
        items.append(f'{count} individual slot(s)')
    return {'maintenance_items': items}
