# Fresh CODEX AI platform

Fresh Flask + SQLite platform using the black/blue dotted visual design and six-item bottom navigation shown in the supplied screenshots.

## Run in Termux

```bash
cd ~/codex700_fresh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Admin

Create an admin from the same project by setting credentials and visiting `/admin/create` once:

```bash
export ADMIN_PHONE='your-admin-phone'
export ADMIN_PASSWORD='your-admin-password'
```

Then open `/admin/create` while the server is running.

## Notes

- Registration, login, referral capture, salary/reward claims, settings, gift codes, raffle eligibility, AI purchases, deposits, withdrawals, support and admin transaction approval are implemented.
- Deposit/withdrawal pages record requests; they do not connect to MTN/Airtel/payment processors until a real provider is configured.
- AI income shown in the account is calculated from purchased machine records; no external mining hardware or blockchain connection is assumed.
- No external fonts, analytics, or remote UI libraries are used, so the interface does not wait for third-party assets to render.
