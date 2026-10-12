"""Run with:  python manage.py test      (Django builds a temporary empty database, so your real data is never touched)."""
import random

from django.test import TestCase
from django.urls import reverse

from . import services as svc
from .models import AVAILABLE, MAINTENANCE, OCCUPIED, Admin, Booking, Entrance, Level, Slot


def layout(names=('South', 'East', 'North'), levels=3, per=50):
    svc.build_layout(list(names), levels, per)


class RuleTests(TestCase):
    def setUp(self):
        layout()

    def raises(self, fn, *a):
        with self.assertRaises(svc.RuleError):
            fn(*a)

    def test_layout_is_data_not_code(self):
        self.assertEqual(Slot.objects.count(), 450)
        layout(['Main'], 1, 30)                                   # a different mall: one entrance, 30 slots
        self.assertEqual((Entrance.objects.count(), Level.objects.count(), Slot.objects.count()), (1, 1, 30))

    def test_book_every_slot_codes_unique_and_random(self):
        for s in list(Slot.objects.all()):
            svc.book_slot(s.pk)
        codes = list(Slot.objects.values_list('code', flat=True))
        self.assertEqual(len(set(codes)), 450)
        self.assertTrue(all(len(c) == 6 for c in codes))
        first = codes[:20]
        self.assertFalse(first == sorted(first))                    # not sequential

    def test_double_booking_rejected(self):
        s = Slot.objects.first(); svc.book_slot(s.pk)
        self.raises(svc.book_slot, s.pk)

    def test_exit_rules(self):
        a, b = Slot.objects.filter(entrance__name='South').first(), Slot.objects.filter(entrance__name='East').first()
        ba, bb = svc.book_slot(a.pk), svc.book_slot(b.pk)
        south, east = Entrance.objects.get(name='South'), Entrance.objects.get(name='East')
        self.raises(svc.verify_exit, south.pk, a.label, 'ZZZZZZ')            # wrong code
        self.raises(svc.verify_exit, south.pk, a.label, bb.code)             # another slot's code
        self.raises(svc.verify_exit, east.pk, a.label, ba.code)              # wrong gate
        self.raises(svc.verify_exit, south.pk, 'X-L9-999', ba.code)          # unknown slot
        a.refresh_from_db(); self.assertEqual(a.status, OCCUPIED)           # still occupied after all the failures
        done = svc.verify_exit(south.pk, a.label.lower(), ba.code.lower())   # correct gate + code (case insensitive)
        a.refresh_from_db()
        self.assertEqual((a.status, a.code), (AVAILABLE, None))
        self.assertEqual(done.released_by, 'driver'); self.assertIsNotNone(done.exited_at)
        self.raises(svc.verify_exit, south.pk, a.label, ba.code)             # used code cannot be reused

    def test_rebooking_issues_new_code(self):
        s = Slot.objects.first(); first = svc.book_slot(s.pk)
        svc.verify_exit(s.entrance_id, s.label, first.code)
        self.assertNotEqual(svc.book_slot(s.pk).code, first.code)

    def test_admin_release_without_code(self):
        s = Slot.objects.first(); svc.book_slot(s.pk); svc.release_slot(s.pk)
        s.refresh_from_db(); self.assertEqual(s.status, AVAILABLE)
        self.assertEqual(Booking.objects.get().released_by, 'admin')

    def test_maintenance_blocks_tickets(self):
        e, l = Entrance.objects.first(), Level.objects.first()
        svc.toggle_status('entrance', e.pk); self.raises(svc.book_slot, Slot.objects.filter(entrance=e).first().pk); svc.toggle_status('entrance', e.pk)
        svc.toggle_status('level', l.pk); self.raises(svc.book_slot, Slot.objects.filter(level=l).first().pk); svc.toggle_status('level', l.pk)
        s = Slot.objects.first(); svc.toggle_status('slot', s.pk); self.raises(svc.book_slot, s.pk)
        self.assertEqual(Slot.objects.get(pk=s.pk).status, MAINTENANCE)
        self.assertEqual(svc.bookable_slots().count(), 449)                 # maintenance slot is not counted as available

    def test_layout_can_change(self):
        e, l = Entrance.objects.first(), Level.objects.first()
        svc.set_slot_count(e.pk, l.pk, 55); self.assertEqual(Slot.objects.filter(entrance=e, level=l).count(), 55)
        svc.set_slot_count(e.pk, l.pk, 50)
        svc.add_level(10); svc.add_entrance('West', 10)
        self.assertEqual(Slot.objects.count(), 450 + 30 + 40)
        svc.remove_area('level', Level.objects.last().pk)
        self.assertEqual(Level.objects.count(), 3)

    def test_occupied_slots_are_protected(self):
        e, l = Entrance.objects.first(), Level.objects.first()
        for s in Slot.objects.filter(entrance=e, level=l):
            svc.book_slot(s.pk)
        self.raises(svc.set_slot_count, e.pk, l.pk, 49)
        self.raises(svc.remove_area, 'entrance', e.pk)
        self.raises(svc.build_layout, ['X'], 1, 5)

    def test_stress_8000_random_booking_attempts(self):
        ids = list(Slot.objects.values_list('pk', flat=True)); ok = 0
        for _ in range(8000):
            try:
                svc.book_slot(random.choice(ids)); ok += 1
            except svc.RuleError:
                pass
        self.assertEqual(ok, 450)
        self.assertEqual(Slot.objects.filter(status=OCCUPIED).count(), 450)
        self.assertEqual(Slot.objects.values('code').distinct().count(), 450)
        self.assertEqual(Booking.objects.count(), 450)


class ViewTests(TestCase):
    def setUp(self):
        layout(['South', 'East'], 2, 10)
        self.admin = Admin.objects.create_user('ADM900', 'Test Admin', 'secret123', is_staff=True, is_superuser=True)

    def test_admin_pages_need_login(self):
        for name in ('dashboard', 'status', 'manage', 'admins'):
            r = self.client.get(reverse(name))
            self.assertRedirects(r, f"{reverse('admin_login')}?next={reverse(name)}", fetch_redirect_response=False)

    def test_login_and_status_tables(self):
        self.assertFalse(self.client.login(username='nobody', password='x'))
        r = self.client.post(reverse('admin_login'), {'employee_number': 'adm900', 'password': 'secret123'})   # case-insensitive
        self.assertRedirects(r, reverse('dashboard'))
        slot = Slot.objects.first(); booking = svc.book_slot(slot.pk)
        page = self.client.get(reverse('status_list', args=['occupied']))
        self.assertContains(page, slot.label); self.assertContains(page, booking.code)      # admin sees the code
        self.assertContains(self.client.get(reverse('dashboard')), 'TA')                      # avatar initials

    def test_drivers_never_see_codes(self):
        slot = Slot.objects.first(); booking = svc.book_slot(slot.pk)
        self.assertNotContains(self.client.get(reverse('book_slots', args=[slot.entrance_id, slot.level_id])), booking.code)
        self.assertNotContains(self.client.get(reverse('home')), booking.code)

    def test_full_driver_journey(self):
        slot = Slot.objects.filter(entrance__name='East').first()
        r = self.client.post(reverse('book_confirm', args=[slot.pk])); self.assertRedirects(r, reverse('book_receipt'))
        booking = Booking.objects.get(); receipt = self.client.get(reverse('book_receipt'))
        self.assertContains(receipt, booking.code); self.assertContains(receipt, 'East Exit')
        south, east = Entrance.objects.get(name='South'), Entrance.objects.get(name='East')
        bad_gate = self.client.post(reverse('exit_verify', args=[south.pk]), {'label': slot.label, 'code': booking.code})
        self.assertContains(bad_gate, 'Wrong exit gate')
        bad_code = self.client.post(reverse('exit_verify', args=[east.pk]), {'label': slot.label, 'code': 'WRONG1'})
        self.assertContains(bad_code, 'does not match')
        ok = self.client.post(reverse('exit_verify', args=[east.pk]), {'label': slot.label, 'code': booking.code})
        self.assertRedirects(ok, reverse('exit_receipt'))
        self.assertContains(self.client.get(reverse('exit_receipt')), 'Time parked')
        slot.refresh_from_db(); self.assertEqual(slot.status, AVAILABLE)

    def test_maintenance_banner_and_manage_actions(self):
        self.client.force_login(self.admin)
        e = Entrance.objects.first()
        self.client.post(reverse('manage_action', args=['entrance_toggle']), {'id': e.pk})
        self.assertContains(self.client.get(reverse('home')), 'Maintenance in progress')
        r = self.client.post(reverse('manage_action', args=['quick']), {'names': 'Main', 'levels': '1', 'per': '30'}, follow=True)
        self.assertEqual(Slot.objects.count(), 30); self.assertContains(r, 'Built 30 slots')

    def test_cannot_remove_self_or_last_admin(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_remove', args=[self.admin.pk]))
        self.assertEqual(Admin.objects.count(), 1)
