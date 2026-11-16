# Congressional Paper Trading Platform

A Django REST backend for paper trading, portfolio management, and tracking congressional stock trades (STOCK Act disclosures) across the securities you pick.

**Stack:** Django · Django REST Framework · PostgreSQL · Docker · AWS (deploy target)

## Features

- **Paper trading:** each portfolio starts with simulated cash. You place market orders that fill at the security's last price.
- **Transactional order processing:** every order runs inside one database transaction (`trading/services.py`). The portfolio row is locked with `SELECT … FOR UPDATE`, so concurrent orders on the same portfolio run one at a time. Cash, holdings, the order, and its ledger entry commit together or not at all. Orders without enough cash or shares are saved as `REJECTED` and change nothing.
- **Relational schema:** `User → Portfolio → Holding / Order → Transaction`, plus `Security`, `WatchlistItem`, `CongressMember`, and `CongressionalTrade`. Database `CHECK` and `UNIQUE` constraints guard invariants such as non-negative cash, positive holdings, and no duplicate disclosures.
- **Congressional activity:** import disclosure CSVs, filter trades by ticker, member, type, or date, and get one feed of congressional trades for every security on your watchlist.
- **Token auth:** register, get a token, and send `Authorization: Token <token>`.

## Quick start (Docker + PostgreSQL)

```bash
docker compose up --build
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser   # optional, for /admin
```

The API runs at http://localhost:8000/api/.

## Quick start (local, SQLite)

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Set `DATABASE_URL=postgres://…` to use PostgreSQL instead of SQLite.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create an account (`username`, `email`, `password`) |
| POST | `/api/auth/token/` | Get an auth token |
| GET | `/api/securities/?q=` | Search securities |
| GET | `/api/securities/{ticker}/congressional-trades/` | Congressional trades for one ticker |
| GET/POST | `/api/portfolios/` | List or create portfolios |
| GET | `/api/portfolios/{id}/` | Cash, holdings, market value, unrealized P&L |
| GET/POST | `/api/portfolios/{id}/orders/` | Order history, or place an order (`ticker`, `side`, `quantity`) |
| GET | `/api/portfolios/{id}/transactions/` | Transaction ledger |
| GET/POST/DELETE | `/api/watchlist/` | Manage watched securities |
| GET | `/api/watchlist/congressional-activity/` | Congressional trades across your watchlist |
| GET | `/api/congress/trades/?ticker=&member=&type=&since=` | Filter all disclosures |
| GET | `/api/congress/members/` and `/{id}/trades/` | Members, ranked by trade count |

### Example

```bash
curl -X POST localhost:8000/api/auth/register/ -d username=zach -d email=z@example.com -d password=changeme123
TOKEN=$(curl -s -X POST localhost:8000/api/auth/token/ -d username=zach -d password=changeme123 | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -X POST localhost:8000/api/portfolios/ -H "Authorization: Token $TOKEN" -d name=Main
curl -X POST localhost:8000/api/portfolios/1/orders/ -H "Authorization: Token $TOKEN" -d ticker=NVDA -d side=BUY -d quantity=10
```

## Data

- `sample_data/congressional_trades.csv` holds **fictional** members and trades for development only.
- Real disclosures can be loaded from any CSV with these columns: `member, chamber, party, state, ticker, type, transaction_date, disclosure_date, amount, owner`. Amount ranges like `$15,001 - $50,000` are parsed automatically.
  ```bash
  python manage.py import_congress_trades path/to/disclosures.csv
  ```
- `python manage.py simulate_prices` applies a random-walk price tick, standing in for a market data feed. Run it on a schedule (cron or EventBridge) to move prices.

## Deploying to AWS

1. Build the image and push it to **ECR**.
2. Create a **PostgreSQL RDS** instance.
3. Run the container on **ECS Fargate** (or App Runner / Elastic Beanstalk). Use the environment variables in `.env.example`, and keep `DJANGO_SECRET_KEY` and `DATABASE_URL` in Secrets Manager.
4. The container runs migrations on start. Point the ALB health check at `/health/`.

## Tests

```bash
python manage.py test
```

The tests cover order fills, weighted average cost, rejections with no side effects, per-user portfolio isolation, importer idempotency, and API filters. GitHub Actions runs them against PostgreSQL.
