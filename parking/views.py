"""VIEWS: each function receives a web request, uses services.py for the rules, and fills a template."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services as svc
from .models import AVAILABLE, OCCUPIED, OPEN, Admin, Booking, Entrance, Level, Slot


# ======================================================================= DRIVER SIDE
def home(request):
    """Every number here is COUNTED from the slots table; nothing is stored or typed in."""
    free = svc.bookable_slots()
    stats = [{'entrance': e, 'free': free.filter(entrance=e).count()} for e in Entrance.objects.all()]
    return render(request, 'parking/home.html', {'available': free.count(), 'total': Slot.objects.count(), 'stats': stats})


def book_entrance(request):
    rows = []
    for e in Entrance.objects.all():
        free = svc.bookable_slots().filter(entrance=e).count()
        rows.append({'entrance': e, 'free': free, 'off': e.status != OPEN or free == 0})
    return render(request, 'parking/book_entrance.html', {'rows': rows})


def book_level(request, eid):
    entrance = get_object_or_404(Entrance, pk=eid)
    if entrance.status != OPEN:
        messages.error(request, 'This entrance is under maintenance.')
        return redirect('book_entrance')
    rows = []
    for l in Level.objects.all():
        free = svc.bookable_slots().filter(entrance=entrance, level=l).count()
        rows.append({'level': l, 'free': free, 'off': l.status != OPEN or free == 0})
    return render(request, 'parking/book_level.html', {'entrance': entrance, 'rows': rows})


def book_slots(request, eid, lid):
    entrance, level = get_object_or_404(Entrance, pk=eid), get_object_or_404(Level, pk=lid)
    slots = list(Slot.objects.filter(entrance=entrance, level=level))
    can_book = entrance.status == OPEN and level.status == OPEN
    free = sum(1 for s in slots if s.status == AVAILABLE) if can_book else 0
    return render(request, 'parking/book_slots.html', {'entrance': entrance, 'level': level, 'slots': slots, 'can_book': can_book, 'free': free})


def book_confirm(request, pk):
    slot = get_object_or_404(Slot.objects.select_related('entrance', 'level'), pk=pk)
    if request.method == 'POST':
        try:
            booking = svc.book_slot(slot.pk)
        except svc.RuleError as e:
            messages.error(request, str(e))
            return redirect('book_slots', slot.entrance_id, slot.level_id)
        request.session['receipt_id'] = booking.pk          # the code is shown only to the browser that booked
        return redirect('book_receipt')
    if slot.status != AVAILABLE:
        messages.error(request, 'That slot is not available.')
        return redirect('book_slots', slot.entrance_id, slot.level_id)
    return render(request, 'parking/book_confirm.html', {'slot': slot})


def book_receipt(request):
    booking = Booking.objects.filter(pk=request.session.get('receipt_id')).first()
    if booking is None:
        return redirect('home')
    return render(request, 'parking/book_receipt.html', {'b': booking})


def exit_gate(request):
    return render(request, 'parking/exit_gate.html', {'entrances': Entrance.objects.all()})


def exit_verify(request, eid):
    entrance = get_object_or_404(Entrance, pk=eid)
    ctx = {'entrance': entrance}
    if request.method == 'POST':
        label, code = request.POST.get('label', ''), request.POST.get('code', '')
        try:
            booking = svc.verify_exit(entrance.pk, label, code)
        except svc.RuleError as e:
            ctx.update(error=str(e), label=label, code=code)
        else:
            request.session['exit_id'] = booking.pk
            return redirect('exit_receipt')
    return render(request, 'parking/exit_verify.html', ctx)


def exit_receipt(request):
    booking = Booking.objects.filter(pk=request.session.get('exit_id')).first()
    if booking is None or booking.exited_at is None:
        return redirect('home')
    minutes = max(0, round((booking.exited_at - booking.entered_at).total_seconds() / 60))
    parked = f'{minutes} min' if minutes < 60 else f'{minutes // 60} h {minutes % 60} min'
    return render(request, 'parking/exit_receipt.html', {'b': booking, 'parked': parked})


# ======================================================================= ADMIN SIDE
def admin_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('employee_number', '').strip(), password=request.POST.get('password', ''))
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next') or 'dashboard')
        error = 'Invalid employee number or password.'
    return render(request, 'parking/admin_login.html', {'error': error})


@require_POST
def admin_logout(request):
    logout(request)
    return redirect('home')


@login_required
def dashboard(request):
    return render(request, 'parking/dashboard.html', {'available': svc.bookable_slots().count(), 'occupied': Slot.objects.filter(status=OCCUPIED).count(), 'admins': Admin.objects.count()})


@login_required
def status(request):
    return render(request, 'parking/status.html', {'available': svc.bookable_slots().count(), 'occupied': Slot.objects.filter(status=OCCUPIED).count()})


@login_required
def status_list(request, kind):
    if kind not in ('available', 'occupied'):
        raise Http404
    qs = Slot.objects.filter(status=OCCUPIED) if kind == 'occupied' else svc.bookable_slots()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(label__icontains=q) | Q(entrance__name__icontains=q) | Q(code__icontains=q))
    total = qs.count()
    return render(request, 'parking/status_list.html', {'kind': kind, 'slots': qs.select_related('entrance', 'level')[:400], 'total': total, 'q': q})


@login_required
@require_POST
def release(request, pk):
    try:
        svc.release_slot(pk)
        messages.success(request, 'Slot released by admin override.')
    except svc.RuleError as e:
        messages.error(request, str(e))
    return redirect('status_list', 'occupied')


@login_required
def manage(request):
    entrances = list(Entrance.objects.annotate(total=Count('slots')))
    levels = list(Level.objects.annotate(total=Count('slots')))
    counts = {(r['entrance_id'], r['level_id']): r['n'] for r in Slot.objects.values('entrance_id', 'level_id').annotate(n=Count('pk'))}
    matrix = [{'level': l, 'cells': [{'entrance': e, 'count': counts.get((e.pk, l.pk), 0)} for e in entrances]} for l in levels]
    sel_e = int(request.GET.get('e') or (entrances[0].pk if entrances else 0))
    sel_l = int(request.GET.get('l') or (levels[0].pk if levels else 0))
    first = counts.get((entrances[0].pk, levels[0].pk), 30) if entrances and levels else 30
    return render(request, 'parking/manage.html', {
        'entrances': entrances, 'levels': levels, 'matrix': matrix, 'sel_e': sel_e, 'sel_l': sel_l,
        'slots': Slot.objects.filter(entrance_id=sel_e, level_id=sel_l),
        'quick_names': ', '.join(e.name for e in entrances), 'quick_levels': len(levels) or 1, 'quick_per': first})


@login_required
@require_POST
def manage_action(request, action):
    """One small handler for every button on the Slot Management page."""
    p = request.POST
    try:
        if action == 'quick':
            msg = f"Built {svc.build_layout(p.get('names', '').split(','), p.get('levels'), p.get('per'))} slots."
        elif action == 'entrance_add':
            svc.add_entrance(p.get('name'), p.get('per')); msg = 'Entrance added.'
        elif action == 'level_add':
            svc.add_level(p.get('per')); msg = 'Level added.'
        elif action in ('entrance_toggle', 'level_toggle', 'slot_toggle'):
            svc.toggle_status(action.split('_')[0], p.get('id')); msg = 'Status changed.'
        elif action in ('entrance_delete', 'level_delete'):
            svc.remove_area(action.split('_')[0], p.get('id')); msg = 'Removed.'
        elif action == 'set_count':
            svc.set_slot_count(p.get('entrance'), p.get('level'), p.get('count')); msg = 'Slots updated.'
        else:
            raise Http404
        messages.success(request, msg)
    except svc.RuleError as e:
        messages.error(request, str(e))
    return redirect(f"{reverse('manage')}?e={p.get('e', '')}&l={p.get('l', '')}")


@login_required
def admins(request):
    return render(request, 'parking/admins.html', {'admins': Admin.objects.order_by('full_name')})


@login_required
@require_POST
def admin_add(request):
    try:
        svc.add_admin(request.POST.get('employee_number'), request.POST.get('full_name'), request.POST.get('password'))
        messages.success(request, 'Admin added.')
    except svc.RuleError as e:
        messages.error(request, str(e))
    return redirect('admins')


@login_required
@require_POST
def admin_remove(request, pk):
    try:
        svc.remove_admin(request.user, pk)
        messages.success(request, 'Admin removed.')
    except svc.RuleError as e:
        messages.error(request, str(e))
    return redirect('admins')
