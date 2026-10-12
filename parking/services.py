"""BUSINESS RULES. Views call these functions and never touch the rules themselves, which keeps the rules easy to explain and test.
RuleError carries a message that is safe to show to the user."""
import secrets

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import AVAILABLE, MAINTENANCE, OCCUPIED, OPEN, Admin, Booking, Entrance, Level, Slot

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'      # no O/0 or I/1 so codes are easy to read


class RuleError(Exception):
    pass


def positive_int(value, what, minimum=1):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise RuleError(f'{what} must be a whole number.')
    if n < minimum:
        raise RuleError(f'{what} must be at least {minimum}.')
    return n


# ---------------------------------------------------------------- verification code
def generate_code():
    """RANDOM 6-character code from the operating system's secure random source (secrets module).
    The exists() check is only a safety net so two cars parked at the same time never hold the same code."""
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not Slot.objects.filter(code=code).exists():
            return code


# ---------------------------------------------------------------- queries used for the numbers on screen
def bookable_slots():
    """A slot can be given out only if it is free AND its entrance AND its level are open (not under maintenance)."""
    return Slot.objects.filter(status=AVAILABLE, entrance__status=OPEN, level__status=OPEN)


def has_occupied(**filters):
    return Slot.objects.filter(status=OCCUPIED, **filters).exists()


# ---------------------------------------------------------------- layout (nothing hard-coded)
def make_label(entrance, level, number):
    return f'{entrance.prefix}-L{level.number}-{number:03d}'


def add_slots(entrance, level, count):
    """Add `count` new slots; numbering continues after the highest existing number."""
    top = Slot.objects.filter(entrance=entrance, level=level).aggregate(m=Max('number'))['m'] or 0
    Slot.objects.bulk_create([Slot(entrance=entrance, level=level, number=top + i, label=make_label(entrance, level, top + i))
                              for i in range(1, count + 1)])


def _new_entrance(name):
    name = (name or '').strip()
    if not name:
        raise RuleError('Enter an entrance name.')
    if Entrance.objects.filter(name__iexact=name).exists():
        raise RuleError('That entrance already exists.')
    prefix, i = name[0].upper(), 1
    while Entrance.objects.filter(prefix=prefix).exists():
        i += 1
        prefix = f'{name[0].upper()}{i}'
    return Entrance.objects.create(name=name, prefix=prefix)


def _new_level():
    number = (Level.objects.aggregate(m=Max('number'))['m'] or 0) + 1
    return Level.objects.create(number=number, name=f'Level {number}')


@transaction.atomic
def build_layout(names, levels, per_level):
    """Rebuild the whole car park: any number of entrances, levels and slots (e.g. one entrance, one level, 30 slots)."""
    names = [n.strip() for n in names if n.strip()]
    levels, per_level = positive_int(levels, 'Levels'), positive_int(per_level, 'Slots per level')
    if not names:
        raise RuleError('Enter at least one entrance.')
    if has_occupied():
        raise RuleError('Release all occupied slots before rebuilding.')
    Slot.objects.all().delete(); Entrance.objects.all().delete(); Level.objects.all().delete()
    entrances = [_new_entrance(n) for n in names]
    level_rows = [_new_level() for _ in range(levels)]
    for e in entrances:
        for l in level_rows:
            add_slots(e, l, per_level)
    return Slot.objects.count()


@transaction.atomic
def add_entrance(name, per_level):
    per_level = positive_int(per_level, 'Slots per level')
    entrance = _new_entrance(name)
    for level in Level.objects.all():
        add_slots(entrance, level, per_level)


@transaction.atomic
def add_level(per_entrance):
    per_entrance = positive_int(per_entrance, 'Slots per entrance')
    level = _new_level()
    for entrance in Entrance.objects.all():
        add_slots(entrance, level, per_entrance)


@transaction.atomic
def set_slot_count(entrance_id, level_id, wanted):
    """Make an entrance+level have exactly `wanted` slots. Removing never touches occupied slots."""
    wanted = positive_int(wanted, 'Slot count', minimum=0)
    entrance, level = Entrance.objects.get(pk=entrance_id), Level.objects.get(pk=level_id)
    current = Slot.objects.filter(entrance=entrance, level=level).count()
    if wanted > current:
        add_slots(entrance, level, wanted - current)
    elif wanted < current:
        ids = list(Slot.objects.filter(entrance=entrance, level=level).exclude(status=OCCUPIED)
                   .order_by('-number').values_list('pk', flat=True)[:current - wanted])
        if len(ids) < current - wanted:
            raise RuleError('Cannot go that low: occupied slots cannot be removed.')
        Slot.objects.filter(pk__in=ids).delete()


MODELS = {'entrance': Entrance, 'level': Level, 'slot': Slot}


def toggle_status(kind, pk):
    """Maintenance on/off for an entrance, a level or a single slot."""
    obj = MODELS[kind].objects.get(pk=pk)
    if kind == 'slot':
        if obj.status == OCCUPIED:
            raise RuleError('Occupied slots cannot be changed.')
        obj.status = AVAILABLE if obj.status == MAINTENANCE else MAINTENANCE
    else:
        obj.status = MAINTENANCE if obj.status == OPEN else OPEN
    obj.save(update_fields=['status'])
    return obj


def remove_area(kind, pk):
    """Delete an entrance or level (its slots are deleted with it)."""
    field = 'entrance_id' if kind == 'entrance' else 'level_id'
    if has_occupied(**{field: pk}):
        raise RuleError('It has occupied slots. Release them first.')
    MODELS[kind].objects.filter(pk=pk).delete()


# ---------------------------------------------------------------- booking and exit
@transaction.atomic
def book_slot(slot_id):
    """Give a driver a slot. The final UPDATE only succeeds if the slot is STILL available, so two drivers
    choosing the same slot at the same moment can never both get it."""
    slot = Slot.objects.select_related('entrance', 'level').filter(pk=slot_id).first()
    if slot is None:
        raise RuleError('Slot does not exist.')
    if slot.entrance.status != OPEN:
        raise RuleError('This entrance is under maintenance.')
    if slot.level.status != OPEN:
        raise RuleError('This level is under maintenance.')
    if slot.status == MAINTENANCE:
        raise RuleError('This slot is under maintenance.')
    code, now = generate_code(), timezone.now()
    taken = Slot.objects.filter(pk=slot.pk, status=AVAILABLE).update(status=OCCUPIED, code=code, booked_at=now)
    if taken == 0:
        raise RuleError('That slot was just taken. Please pick another.')
    return Booking.objects.create(slot_label=slot.label, entrance_name=slot.entrance.name, code=code, entered_at=now)


def _free_slot(slot, released_by):
    booking = Booking.objects.filter(slot_label=slot.label, exited_at__isnull=True).order_by('-pk').first()
    slot.status, slot.code, slot.booked_at = AVAILABLE, None, None      # the code is destroyed, so it can never be reused
    slot.save(update_fields=['status', 'code', 'booked_at'])
    if booking:
        booking.exited_at, booking.released_by = timezone.now(), released_by
        booking.save(update_fields=['exited_at', 'released_by'])
    return booking


@transaction.atomic
def verify_exit(entrance_id, label, code):
    """Exit rule. Four things must all be true:
    1) the slot exists  2) it is occupied  3) the exit gate chosen = the entrance used  4) the code = the code linked to this slot."""
    slot = Slot.objects.select_related('entrance').filter(label=(label or '').strip().upper()).first()
    if slot is None:
        raise RuleError('Slot number not found.')
    if slot.status != OCCUPIED:
        raise RuleError('This slot is not currently occupied.')
    if slot.entrance_id != int(entrance_id):
        raise RuleError('Wrong exit gate. The exit must match the entrance this vehicle used.')
    if slot.code != (code or '').strip().upper():
        raise RuleError('Verification code does not match this slot.')
    return _free_slot(slot, 'driver')


@transaction.atomic
def release_slot(slot_id):
    """Admin override: free a slot without a code."""
    slot = Slot.objects.filter(pk=slot_id, status=OCCUPIED).first()
    if slot is None:
        raise RuleError('Slot is not occupied.')
    return _free_slot(slot, 'admin')


# ---------------------------------------------------------------- admin accounts
def add_admin(employee_number, full_name, password):
    employee_number, full_name = (employee_number or '').strip(), (full_name or '').strip()
    if not employee_number or not full_name or len(password or '') < 6:
        raise RuleError('Fill all fields. Password needs 6+ characters.')
    if Admin.objects.filter(employee_number__iexact=employee_number).exists():
        raise RuleError('Employee number already exists.')
    Admin.objects.create_user(employee_number, full_name, password, is_staff=True, is_superuser=True)


def remove_admin(requester, pk):
    if str(requester.pk) == str(pk):
        raise RuleError('You cannot remove yourself.')
    if Admin.objects.count() < 2:
        raise RuleError('Cannot remove the last admin.')
    Admin.objects.filter(pk=pk).delete()
