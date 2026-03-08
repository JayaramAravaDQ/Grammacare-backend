# Grammacare-backend

API backend for the GrammaCare AI chatbot. Use this when you want the Next.js frontend to talk to Django instead of Next.js API routes.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
export GEMINI_API_KEY=your_key   # or set in .env
python manage.py migrate
python manage.py runserver
```

Server runs at **http://127.0.0.1:8000**.

## Use with Next.js frontend

In the project root (V219), set:

```bash
# .env.local
GEMINI_API_KEY=your_gemini_key
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Then run the Next.js app (`npm run dev`). The app will use Django for auth, chat, and consultation history.

## API (same shape as Next.js)

- `POST /api/auth/login/` — body: `{ "email", "password" }`
- `POST /api/auth/logout/`
- `GET /api/auth/user/`
- `POST /api/chat/` — body: `{ "action", "patientName", "symptom?", "data?", "lat?", "lon?", "locationSource?" }`
- `GET /api/history/?action=list&username=...` or `?action=get&id=...`
- `POST /api/history/` — body: `{ "action": "save", "consultation" }` or `{ "action": "delete", "id" }`

## Dummy users (same as frontend)

- admin@grammacare.com / admin123
- doctor@grammacare.com / doctor123
- patient@grammacare.com / patient123
- demo@grammacare.com / demo123
