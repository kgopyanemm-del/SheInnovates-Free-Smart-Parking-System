# SmartPark: Parking Slot Management (Node.js + Express + SQLite)

## Run it (VS Code terminal)
```
npm install
npm start          # then open http://localhost:3000
npm test           # database rule tests on 3 different layouts
```
Needs Node 22.13 or newer (SQLite is built in, so there is nothing to compile). The database file `smartpark.db` is created automatically on first run.
Admin login: employee no. `ADM001`, password `admin123` (change it under Admin Accounts).

## Showing the database
Install the **SQLite Viewer** extension in VS Code, then click `smartpark.db` in the file explorer. (Or use DB Browser for SQLite.)
Useful queries (DB Browser: "Execute SQL"):
```sql
SELECT label, code, datetime(booked_at/1000,'unixepoch','localtime') AS booked FROM slots WHERE status='occupied';
SELECT e.name, COUNT(*) AS total, SUM(s.status='available') AS free FROM slots s JOIN entrances e ON e.id=s.entrance_id GROUP BY e.name;
SELECT * FROM bookings ORDER BY id DESC LIMIT 20;
```

## Tables
| Table | Purpose |
|---|---|
| `entrances` | name, prefix (S/E/N), status open/maintenance |
| `levels` | level number, name, status open/maintenance |
| `slots` | entrance, level, number, label (S-L1-001), status (available/occupied/maintenance), current verification code, booked_at |
| `bookings` | history of every entry/exit (code, entered_at, exited_at, released by driver or admin) |
| `admins` | employee number, name, salted scrypt password hash |
| `meta` | remembers the first-run starter layout was created |

## Where things are
| Question | Answer |
|---|---|
| Where are the slots stored? | `slots` table. Nothing is hard-coded: admin screens add/remove entrances, levels, slots. The starter layout (3x3x50) is created once by `build()` in `db.js` and is fully editable. |
| Where is the verification code generated? | `genCode()` in `db.js`: 6 random characters from `crypto.randomInt`. The UNIQUE column on `slots.code` only prevents two active cars sharing a code. |
| Where is the exit check? | `exit()` in `db.js`: slot exists, is occupied, exit gate = entrance used, code = code linked to that slot. Otherwise an error message. |
| How are the numbers on screen calculated? | The browser gets the slot list from `GET /api/state` and counts statuses (`cnt()` in `public/js/app.js`). It refreshes every 5 seconds. |
| Two people book the same slot at once? | `book()` runs in a transaction and uses `UPDATE ... WHERE status='available'`, so only one succeeds. |
| Who can see verification codes? | Only a logged-in admin. The public state sent to drivers has no codes. |
| Maintenance? | Entrance, level or single slot can be set to maintenance. `book()` refuses it and the UI shows a banner. Exits always work. |

## Assumptions
1. A driver must exit through the exit that matches the entrance they used.
2. A slot belongs to one entrance and one level.
3. A code is created per booking and deleted at exit. Re-booking a slot gives a new random code.
4. Admins can release a slot without a code (override), recorded in `bookings.released_by`.
5. Admin sessions are kept in server memory (restarting the server logs admins out).
6. No HTTPS or login rate limiting. Fine for a course project, not for production.

## Folders
`server.js` (routes) · `db.js` (schema + all rules) · `tests/` · `public/` (index.html, css, js/app.js)
