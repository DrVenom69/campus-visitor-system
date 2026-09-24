# Campus Visitor Management and Digital Gate Pass System

Flask + PostgreSQL web app for a university. A visitor asks to visit, an admin reviews the request,
an approved visit gets a digital **QR gate pass**, and security scans it at the gate.

```
Visitor request → Admin review → Approve / Reject → Host assigned → QR gate pass
   → Gate check-in → Campus visit → Gate check-out → Completed
```

**Status flow:** `Pending → Approved → Checked In → Checked Out → Completed` (or `Rejected` / `Cancelled`)

## Run it on Ubuntu (one command)

```bash
unzip campus-visitor-system.zip && cd campus-visitor-system
bash setup_ubuntu.sh        # installs PostgreSQL, creates the DB and .env, the venv, tables, your admin account
source venv/bin/activate
python run.py               # open http://127.0.0.1:5000
```

The script asks for your sudo password once and never overwrites an existing `.env`.
If the database already has tables from an older version it asks before deleting them.

<details>
<summary>Manual setup (what the script does)</summary>

```bash
sudo apt install -y python3 python3-venv python3-pip postgresql
sudo -u postgres psql -c "CREATE USER visitor_admin WITH PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE campus_visitor OWNER visitor_admin;"

python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # put your password and a long random SECRET_KEY in it

flask --app run init-db
flask --app run create-admin
flask --app run seed-demo   # optional sample data
python run.py
```
Without `DATABASE_URL` in `.env` the app uses a local SQLite file, so it still runs.
</details>

## Put it on GitHub (your own commits)

1. On github.com create a **new empty private repository** (no README, no .gitignore).
2. Set your git identity once. The email must be one that is added to your GitHub account:
   ```bash
   git config --global user.name  "Your Name"
   git config --global user.email "your-email@example.com"
   ```
3. Push:
   ```bash
   bash setup_github.sh https://github.com/YOUR-USER/campus-visitor-system.git
   ```
   For HTTPS, GitHub asks for a **Personal Access Token** as the password
   (Settings → Developer settings → Personal access tokens). An SSH URL works too.
4. Repo **Settings → Collaborators** → add your teammates.

The script refuses to run without a git identity, never stages `.env` / `venv/` / database files,
and prints the author of the commit it made. Every push runs the tests on GitHub (`.github/workflows/tests.yml`).

## Who can do what

| Role | Can open |
|---|---|
| **Visitor** (no account) | Home, request form, status lookup, own gate pass |
| **Admin** | Everything: requests queue, approve / reject / cancel, host assignment, gate, history, users |
| **Security** | Dashboard, gate check-in / check-out, inside-campus list, history |
| **Host** | Dashboard and history of visits assigned to them |

Create host / security / admin accounts on the **Users** page (or `flask --app run create-user`).

## The workflow, page by page

| Step | URL | Who |
|---|---|---|
| Request a visit (saved as `Pending`, ID `VR-YYYYMMDD-XXXX`) | `/visit-request` | Anyone |
| Check status with request ID + email, get the pass | `/status` | Anyone |
| Printable QR gate pass | `/pass/<code>` | Whoever holds the link |
| Review queue, approve / reject | `/requests/` | Admin |
| Assign host, cancel, mark completed | `/requests/<id>` | Admin |
| Scan or type a pass code, check in / out | `/gate/` | Admin, Security |
| Who is inside right now | `/gate/inside` | Admin, Security |
| Search all visits | `/history/` | Staff |
| Manage accounts | `/users/` | Admin |

Rules enforced in `app/services.py`: a pass only works on its visit date (Asia/Dhaka time), only once,
only while approved; rejecting needs a reason; cancelling switches the pass off; a visitor already
inside can still check out after midnight.

**Camera scanner:** browsers only allow the camera on `http://localhost`, `http://127.0.0.1` or HTTPS.
Open the app at `127.0.0.1` (not the VM's network IP). The scanner library loads from a CDN, so it needs
internet. Typing the code always works.

## Project layout

```
run.py                     starts the app
setup_ubuntu.sh            one-command setup
setup_github.sh            push to GitHub with your identity
app/
  __init__.py              create_app(), extensions, template filters
  config.py                settings (reads .env)
  constants.py             ROLES, STATUSES, PURPOSES  <- use these, don't retype strings
  models.py                User, Visitor, VisitRequest, HostAssignment, GatePass, CheckInOut
  services.py              business rules: approve, reject, cancel, check_in, check_out ...
  utils.py                 request ID + pass code generators, timezone helpers, @roles_required
  qr.py                    QR image generator
  cli.py                   init-db, create-admin, create-user, seed-demo
  routes/                  one blueprint per area: public, auth, dashboard, requests, users, gate, history
  templates/               public pages (Bootstrap 5) and staff pages (admin/layout.html + custom CSS)
  static/                  css, js (scanner.js)
tests/                     129 tests
```

Routes stay thin. Put rules in `services.py`, keep them tested, and raise `ServiceError` for anything a user can do wrong.

## Tests

```bash
pytest -q                                          # uses in-memory SQLite, takes about 6 seconds
TEST_DATABASE_URL=postgresql://user:pass@localhost/campus_visitor_test pytest -q   # same tests on PostgreSQL
```

## Team workflow

- `main` always runs and passes `pytest`. Do not push to it directly.
- One branch per task: `git checkout -b feature/short-name`, small commits, push, open a pull request, get one review.
- `git pull origin main` before you start.
- New route → new test. Secrets only in `.env`.

## Known limits (good next tasks)

- No email sending: visitors get their pass on the status page.
- No rate limiting on login or the status lookup.
- Tables are created with `create_all`; after changing a model in development run `flask --app run init-db --reset` (deletes data). Add Flask-Migrate before real use.
- `python run.py` is the development server. Use gunicorn behind HTTPS for real deployment.
- Visitor reports / CSV export, visit reminders, and a visitor-side cancel button are not built.
