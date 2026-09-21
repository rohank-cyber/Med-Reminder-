# MedRemind — Streamlit version

A Python + Streamlit rebuild of the uploaded MedRemind React website.

## Included
- Today dashboard
- Medicine cabinet
- Add/delete medicines
- Take / snooze / skip actions
- Stock tracking and refill warnings
- Real dose-history database using SQLite
- Real monthly adherence calendar
- Family/caregiver summary
- Local login/signup-ready architecture (demo account included)
- No Supabase/API required

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Demo login
- Email: `demo@medremind.app`
- Password: `medremind123`

The SQLite database is created automatically at `data/medremind.db`.

## Notes
This version intentionally replaces the original Supabase dependency with local SQLite so it can run without external APIs. For production use, add proper account recovery, encrypted secrets, HTTPS, stronger authentication/session handling, and a server-side database.
