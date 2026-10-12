# SmartPark: Parking Slot Management (Django)

## Run it (Windows PowerShell, from the folder that contains `manage.py`)
```
python -m venv venv                  # 1. create the environment (use "py -m venv venv" if "python" is not found)
venv\Scripts\activate                # 2. activate it (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt      # 3. install Django
python manage.py migrate             # 4. create the database tables from models.py
python manage.py seed                # 5. starter layout + first admin (safe to run twice)
python manage.py runserver           # 6. start the site: http://127.0.0.1:8000
python manage.py test                # run the test suite (16 tests, uses a temporary database)
```
If PowerShell blocks `activate`, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
Needs Python 3.12 or newer. Admin login: employee no. `ADM001`, password `admin123` (change it under Admin Accounts).

## Showing the database
The database is the file `db.sqlite3`. Three ways to show it:
1. Open **http://127.0.0.1:8000/django-admin/** and log in: Django's built-in screens list every table (Entrances, Levels, Slots, Bookings, Admins).
2. `python manage.py dbshell` (needs the sqlite3 program), then `SELECT label, code, status FROM parking_slot WHERE status='occupied';`
3. VS Code extension **SQLite Viewer**, click `db.sqlite3`.

## How Django maps to this project (MTV)
| Django part | File | What it does here |
|---|---|---|
| Models (database tables) | `parking/models.py` | `Entrance`, `Level`, `Slot`, `Booking`, `Admin` |
| Business rules | `parking/services.py` | `generate_code`, `book_slot`, `verify_exit`, `release_slot`, `build_layout`, `set_slot_count` ... |
| Views (controllers) | `parking/views.py` | Receive a request, call a rule, pick a template |
| URLs | `parking/urls.py` | Maps web addresses to views |
| Templates (screens) | `parking/templates/parking/*.html` | HTML with Django tags |
| Static files | `parking/static/parking/style.css` | Styling |
| Settings | `smartpark/settings.py` | Database, installed apps, custom admin user |
| Migrations | `parking/migrations/` | Generated instructions that create the tables |
| Seed command | `parking/management/commands/seed.py` | Used by `python manage.py seed` |
| Database browser | `parking/admin.py` | Registers tables for `/django-admin/` |
| Tests | `parking/tests.py` | `python manage.py test` |

## Questions your lecturer may ask
| Question | Answer |
|---|---|
| Are the slots hard-coded? | No. Slots are rows in the `Slot` table. The starter 3x3x50 layout is created once by `seed` (calls `build_layout`) and is editable from Slot Management. |
| Where is the verification code generated? | `generate_code()` in `parking/services.py`: 6 random characters from Python's `secrets` module. The unique column only stops two active cars sharing a code. |
| What happens to a code when a slot is re-booked? | The code is deleted at exit (`_free_slot`) and `book_slot` generates a new one. |
| Where is the exit check? | `verify_exit()`: slot exists, is occupied, exit gate = entrance used, code = that slot's code. |
| Where do the numbers on screen come from? | Counted from the database each time: `bookable_slots().count()` in `views.py`. |
| Two drivers book the same slot at once? | `book_slot` ends with `UPDATE ... WHERE status='available'` inside a transaction; only one update succeeds. |
| Who can see codes? | Only logged-in admins. The driver pages never include other cars' codes (tested). |
| Maintenance? | `toggle_status()` for an entrance, level or slot. `book_slot` refuses it, `context_processors.py` shows the banner. Exits keep working. |
| How are passwords stored? | Django hashes them (PBKDF2 with salt). |

## Assumptions
1. A driver must exit through the exit that matches the entrance used.
2. A slot belongs to one entrance and one level.
3. A code is created per booking and destroyed at exit; re-booking gives a new random code.
4. Exits always work, even during maintenance. Maintenance stops new tickets only.
5. Admins can release a slot without a code (recorded as `released_by = admin`).
6. Every account in the Admin table is an administrator with full access.
7. Available slots have no code (a code exists only after booking).
8. Times use the server clock, shown in Africa/Johannesburg time (`TIME_ZONE` in settings).
9. Default password and `SECRET_KEY` are for development only. No HTTPS or login-attempt limit.
