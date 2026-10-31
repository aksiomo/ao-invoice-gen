init:
  cp .env.example .env

run:
  .python/bin/uvicorn app.main:app --reload
