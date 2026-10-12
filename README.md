# SmartPark: Parking Slot Management

## Run it
- Open the folder in VS Code, right-click `index.html` -> **Open with Live Server** (or just double-click `index.html`).
- Admin login: employee no. `ADM001`, password `admin123` (change it under Admin Accounts).
- Tests: `node tests/run-tests.js` (needs Node 18+). Also available in the app: Admin Dashboard -> Run system self-test.

## Files
| File | What it does |
|---|---|
| `js/core.js` | All rules: `build()` (layout), `book()` (ticket issuing), `genCode()` (verification code), `verifyExit()` (exit gate + code check), `setCount()` (add/remove slots), `selfTest()` |
| `js/app.js` | Screens, button actions, storage (localStorage), admin login |
| `css/style.css` | Styling |
| `tests/run-tests.js` | Runs the self-test on 3 different layouts |

## Nothing hard-coded
Entrances, levels and slots are rows in the data object (`DB`), created/edited from Admin -> Slot Management. The first-run layout (3 entrances x 3 levels x 50 slots) is only a starter, built by the `build()` call in `js/app.js` (boot section). "Quick setup" rebuilds any layout (e.g. 1 entrance, 30 slots). Counts on screen are computed from the data (`cnt()` in app.js).

## Assumptions
1. A driver enters through one entrance and must leave through the matching exit.
2. A slot belongs to one entrance and one level.
3. A verification code is created per booking (6 chars, unique among active codes) and destroyed at exit. Re-booking a slot issues a new code.
4. Maintenance (entrance, level or slot) stops tickets being issued. Exits always stay open.
5. Admins can release a slot without a code (override).
6. localStorage stands in for the database. Replace `save()` and the load in the boot section with real DB calls.
7. Passwords are stored as SHA-256 hashes (a real deployment should use salted server-side hashing).
