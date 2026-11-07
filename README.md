# VakeelSevak

AI-first practice and case management for Indian advocates. React web, React Native mobile, FastAPI, PostgreSQL.

## Run it

```bash
make db            # PostgreSQL in Docker
make api-install
make migrate
make seed          # sample office, clients, cases, hearings
make api           # http://localhost:8000/docs
make web           # http://localhost:5173  (component gallery)
make mobile        # Expo; set EXPO_PUBLIC_API_URL for a physical phone
make test
```

After `make seed`, sign in with `menon@example.in` and password `ChangeMe#2026` (sample data only). Other sample
users are listed in `docs/ARCHITECTURE.md`.

Copy `apps/api/.env.example` to `apps/api/.env` to change the product name, languages or database.

See `docs/FEATURES.md` for the build order and `docs/ARCHITECTURE.md` for how it fits together.
