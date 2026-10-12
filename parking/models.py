"""DATABASE TABLES. Each class is one table; each attribute is one column.
Nothing about the size of the car park is written here: entrances, levels and slots are ROWS that admins add and remove."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

OPEN, MAINTENANCE = 'open', 'maintenance'
AVAILABLE, OCCUPIED = 'available', 'occupied'
AREA_STATUS = [(OPEN, 'Open'), (MAINTENANCE, 'Under maintenance')]
SLOT_STATUS = [(AVAILABLE, 'Available'), (OCCUPIED, 'Occupied'), (MAINTENANCE, 'Under maintenance')]


class AdminManager(BaseUserManager):
    def get_by_natural_key(self, employee_number):          # employee numbers are not case sensitive at login
        return self.get(employee_number__iexact=employee_number)

    def create_user(self, employee_number, full_name, password=None, **extra):
        if not employee_number:
            raise ValueError('Employee number is required')
        user = self.model(employee_number=employee_number, full_name=full_name, **extra)
        user.set_password(password)                            # stored as a salted PBKDF2 hash, never as plain text
        user.save(using=self._db)
        return user

    def create_superuser(self, employee_number, full_name, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(employee_number, full_name, password, **extra)


class Admin(AbstractBaseUser, PermissionsMixin):
    """Table of administrators. Only people in this table can log in to the admin side."""
    employee_number = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True)
    USERNAME_FIELD = 'employee_number'
    REQUIRED_FIELDS = ['full_name']
    objects = AdminManager()

    def initials(self):                                         # letters shown in the avatar at the top right
        return ''.join(w[0] for w in self.full_name.split())[:2].upper() or '?'

    def __str__(self):
        return f'{self.employee_number} ({self.full_name})'


class Entrance(models.Model):
    name = models.CharField(max_length=60, unique=True)
    prefix = models.CharField(max_length=5, unique=True)      # first part of slot labels, e.g. S in S-L1-001
    status = models.CharField(max_length=12, choices=AREA_STATUS, default=OPEN)

    @property
    def display_name(self):
        return f'{self.name} Entrance'

    @property
    def exit_name(self):                                        # every entrance has its own matching exit
        return f'{self.name} Exit'

    def __str__(self):
        return self.display_name


class Level(models.Model):
    number = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=60)
    status = models.CharField(max_length=12, choices=AREA_STATUS, default=OPEN)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return self.name


class Slot(models.Model):
    entrance = models.ForeignKey(Entrance, on_delete=models.CASCADE, related_name='slots')   # delete an entrance -> its slots go too
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name='slots')
    number = models.PositiveIntegerField()
    label = models.CharField(max_length=30, unique=True)                                      # e.g. S-L1-001
    status = models.CharField(max_length=12, choices=SLOT_STATUS, default=AVAILABLE)
    code = models.CharField(max_length=6, unique=True, null=True, blank=True)                 # verification code of the CURRENT booking
    booked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['entrance_id', 'level_id', 'number']
        constraints = [models.UniqueConstraint(fields=['entrance', 'level', 'number'], name='one_number_per_entrance_level')]

    def __str__(self):
        return self.label


class Booking(models.Model):
    """History: one row per visit. Kept even if the slot or entrance is later deleted."""
    slot_label = models.CharField(max_length=30)
    entrance_name = models.CharField(max_length=60)
    code = models.CharField(max_length=6)
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)
    released_by = models.CharField(max_length=10, blank=True)   # 'driver' (normal exit) or 'admin' (override)

    @property
    def exit_name(self):
        return f'{self.entrance_name} Exit'

    def __str__(self):
        return f'{self.slot_label} {self.entered_at:%Y-%m-%d %H:%M}'
