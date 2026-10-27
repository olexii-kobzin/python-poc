# To fix

Notes from a full review of the project. Written in order of when you will
need each thing, not by how interesting it is.

Legend:
- **MUST** — will break something, or is a security problem
- **SHOULD** — real bug or risk, but nothing is broken today
- **NICE** — cleanup, can wait forever

---

## 1. Do now (small, but security)

- [x] **MUST** `.env` and `.env.test` are saved in git.
  Done: ignored, removed from the index, `.env.example` added. Old commits
  left as is on purpose (test project, secrets are throwaway).
  They contain an RSA private key (`JWT_LOCAL_PRIVATE_KEY`), an HMAC secret
  (`VERSION_TOKEN_SECRET`), a database password, and connection strings with
  passwords inside. They are in two commits: `a44a7f6` and `4220f7e`.
  - Add `.env` and `.env.test` to `.gitignore`
  - `git rm --cached .env .env.test`
  - Make a `.env.example` with the key names but no real values
  - Change the secrets (make new ones)
  - `git rm --cached` does not delete them from old commits. If this repo will
    ever be public, rewrite the history too.

- [x] **SHOULD** Refuse to start if `JWT_LOCAL_PRIVATE_KEY` is set and
  `APP_ENV` is not `local`.
  Right now only `APP_ENV == LOCAL` stops the app from signing its own admin
  tokens (`fast_deps.py:29`). One wrong environment variable turns the API into
  a token factory. Add a check in `conf.py` that raises on startup.

---

## 2. Before GitHub Actions

- [x] **MUST** Tests cannot create their own database.
  `compose.yaml` uses an external network `backend` and has no `postgresql`
  service. No fixture runs the migrations — `alembic upgrade head` only exists
  as a comment (`compose.yaml:56`). This works on your machine because the
  containers already exist. In a CI runner there is nothing there, so the whole
  suite fails.
  Decided: local keeps the external `backend` network. CI gets its own
  `services: postgres:` block in the GitHub Actions job (not `compose.yaml`)
  and runs `alembic upgrade head` as a step before `pytest`. Nothing to change
  in code until the workflow is written.

- [x] **MUST** `anyio` and `cryptography` are imported by tests but are not
  listed as dependencies (`tests/conftest.py:8`, `:10`).
  They work now only because other packages pull them in. Add both to
  `[dependency-groups].dev` in `pyproject.toml`.
  Done: both are in `dev` and `uv.lock` is updated.

- [x] **SHOULD** The production image cannot run by itself.
  `cicd/docker/Dockerfile:45` is `ENTRYPOINT []` and there is no `CMD`.
  Either add a `CMD`, or accept it and always set `command:` in the k8s
  manifest. Just decide on purpose.
  Decided: `ENTRYPOINT []` is gone; the prod stage deliberately has no `CMD`
  (the `CMD ["pytest"]` at line 26 is the test stage). One image serves api,
  consumers and subscribers, so the command is always set at deploy time.

- [x] **NICE** No coverage tool at all. Add `pytest-cov` when you want a number.
  Done: `pytest-cov` in `dev`, `[tool.coverage.*]` in `pyproject.toml`. Not in
  `addopts`, so plain `pytest` stays fast; run `pytest --cov`.

---

## 3. Before Kubernetes

- [x] **MUST** No health endpoints.
  Done: API and workers. `/livez` (no dependencies) and `/readyz` (`SELECT 1`, 503
  on any error) added in `routers/system/health.py`; the api healthcheck in
  `compose.yaml` uses `/readyz`. The API has no AMQP connection (events go
  through the pgqueuer table), so `/readyz` is Postgres-only on purpose.
  Workers: `infra/heartbeat.py` checks SQL (`SELECT 1`) and AMQP
  (`broker.ping`) every 10 s and touches `/tmp/{consumers,subscribers}.alive`;
  the compose healthcheck fails if the file is older than 30 s. Tests in
  `tests/app/routers/test_health.py` and `tests/infra/test_heartbeat.py`.
  For k8s use the same file check as an exec probe.
  There is no `/health`, `/livez` or `/readyz`. `compose.yaml` checks
  `/openapi.json`, which returns 200 even when Postgres is down.
  The `consumers` and `subscribers` processes have no health signal at all, so
  a stuck worker looks fine forever. k8s needs real probes.

- [x] **SHOULD** Graceful shutdown is incomplete.
  Done: `graceful_timeout=settings.amqp_graceful_timeout` in `build_broker()`;
  all three processes call `sa_engine.dispose()`.
  - `RabbitBroker` is built with no `graceful_timeout`
    (`app/subscribers/base.py:40`), so running handlers get cut off instead of
    finishing.
  - Only the API disposes the database engine (`main.py:16-22`). The consumer
    and subscriber processes create an engine and never dispose it.

- [x] **SHOULD** Decide how migrations run.
  Decided: manual (`alembic upgrade head`), not on pod start. The database is
  shared between microservices, so no single service's deploy should migrate it
  automatically. Keep migrations backward compatible, because old pods keep
  running against the new schema.
  Today it is a manual command. In k8s it should be a Job or an init container
  that runs before the app pods start.

- [x] **NICE** Nothing propagates a request id between the three processes.
  Done: the id is a UUID (`infra/request_id.py`; anything else is replaced by a
  new uuid7). The API middleware returns it as `x-request-id`; it travels in
  pgqueuer job `headers` (API and subscribers enqueue), in RabbitMQ message
  headers (consumers publish), and is bound to the log context by the job
  executor and by a router dependency on the subscribers. Scheduled jobs have no
  incoming id, so they get a fresh one per run.
  `main.py:34` binds `x-request-id`, but binds `None` when the header is
  missing, never sends it back in the response, and never puts it into the
  RabbitMQ message or the pgqueuer job. So you cannot follow one request
  across API -> queue -> worker. This will hurt when you are debugging in a
  cluster.

---

## 4. Real bugs and risks in the code

### Database

- [ ] **SHOULD** Three relationships are never used and will crash if anyone
  uses them.
  `domain/entities/customer.py:43`, `domain/entities/account.py:67`, `:143`.
  With async SQLAlchemy, lazy loading does not just get slow — it raises
  `MissingGreenlet`. It is worse because the vendored history recipe sets
  `active_history = True` on all properties
  (`persistence/versioned_history.py:161-162`), so even *assigning* to the
  relationship would try a sync load.
  Fix: delete them, or set `lazy="raise"`.

- [ ] **SHOULD** No naming convention on the metadata.
  Add `MetaData(naming_convention=...)` to `Base`. The migrations already show
  the problem — they mix Postgres auto-names with hand-written names
  (see migration `d0b11413183a`). Autogenerate will keep producing noise until
  this is set.

- [ ] **SHOULD** The ledger verifier does not lock the accounts it picks.
  `infra/repository/ledger_verification.py` selects target accounts with no
  lock and no claim. If two scheduler runs overlap, both process the same
  accounts and crash on a duplicate insert instead of skipping.
  Fix: `SELECT ... FOR UPDATE SKIP LOCKED`, or `ON CONFLICT DO NOTHING`.

- [ ] **NICE** Nine places call `await session.commit()` by hand and nothing
  checks that you did. If one is forgotten, the work is silently thrown away.
  A `session.begin()` dependency or a small Unit of Work object would remove
  this whole class of bug.

- [ ] **NICE** Indexes that are not used:
  - `ix_customer_account_ledger_discrepancy_kind` — `kind` is never filtered on
  - `ix_customer_account_ledger_verified_account_id_verified_at` — queries sort
    by `through_no`, which uses the primary key
  Both only cost write time.

- [ ] **NICE** Migration `f3bbd6b8a2f1:46-59` adds `no` and `balance` as
  NOT NULL with no `server_default`. It only works on an empty table. Fine for
  now, but it is an assumption nobody wrote down.

- [ ] **NICE** `alembic.ini:87` still has the placeholder
  `sqlalchemy.url = driver://user:pass@localhost/dbname`. It is harmless
  because `env.py:48` replaces it, but it is confusing.

### Messages and queues

- [ ] **SHOULD** Dead letters go nowhere.
  `live_queue()` (`app/subscribers/base.py:43`) correctly tells the live queue
  to send rejected messages to `events.dlx`. But no queue is declared or bound
  **to** `events.dlx`. A topic exchange with no binding drops the message
  silently. So a failed message is lost, not parked.
  Fix: declare a dead-letter queue and bind it to `events.dlx` with a matching
  routing key.

- [ ] **NICE** `commands` and `commands.dlx` exchanges are declared
  (`app/subscribers/base.py:16-25`) but no subscriber uses them. Commands go
  through pgqueuer instead. Dead code — delete or use.

- [ ] **NICE** `arguments={"x-dead-letter-exchange": "dlx"}` on the *exchanges*
  (`base.py:20`, `:32`) does nothing. That argument only works on queues, and
  the exchange named `"dlx"` does not exist. Leftover from copy/paste.

- [ ] **SHOULD** `on_customer_created` (`app/subscribers/main.py:52`) checks if
  the customer exists and then inserts. Two messages at the same time will
  raise `IntegrityError`, and the message is then rejected and lost.
  Fix: `INSERT ... ON CONFLICT DO NOTHING`.

- [ ] **SHOULD** Add one test that protects the outbox.
  The whole guarantee depends on `deps.py:27-30` taking the raw asyncpg
  connection out of the SQLAlchemy session, so `enqueue` and `commit` are one
  transaction. If a future pgqueuer version changes this, **nothing will fail
  loudly** — you would silently go back to two separate writes and lose events
  under load.
  Test: enqueue inside a transaction, roll back, check no job row exists.

- [ ] **NICE** `app/consumers/executor.py:26` — a `TerminalJobError` on the
  first try still logs "exhausted" with `attempts: 0`. Misleading log.

- [ ] **NICE** `executor.py:27-34` catches a `RetryRequested` raised by the
  handler and replaces it with its own delay, so the handler's requested delay
  is ignored.

- [ ] **NICE** Schedulers have no error handling
  (`app/consumers/schedulers/main.py`). An exception just escapes, with no
  alert.

### API

- [ ] **SHOULD** `POST /v1/accounts` returns 201 with an empty body and no
  `Location` header (`app/routers/admin/account.py:48`). The id is generated on
  the server, so **the client never finds out the id of what it created**.
  Fix: return the id, or add a `Location` header.

- [ ] **SHOULD** No handler for `IntegrityError`.
  Creating a second account with the same customer + currency hits
  `uq_customer_account_customer_id_currency` and returns a raw 500 instead of
  409 or 422.

- [ ] **SHOULD** `name` search is not escaped
  (`read/repository/account.py:128`):
  `CustomerAccount.name.like(f"%{query.name}%")`.
  This is **not** SQL injection — the value is bound safely. But `%` and `_`
  are LIKE wildcards, so a user searching `_` matches everything and forces a
  full table scan. Also `like` is case sensitive, so `acme` will not find
  `Acme`.
  Fix: escape `\`, `%`, `_` in the input and use `ilike(..., escape="\\")`.

- [ ] **NICE** `DELETE` does not return 404 for an already deleted account,
  but `PATCH` does (`account.py:108` vs `:150`). Make them behave the same.

- [ ] **NICE** Path parameters are named differently on different routes:
  `{account_id}` on update/delete, `{id}` on the ledger routes. Also `id`
  hides the Python builtin.

- [ ] **NICE** The router lives in `routers/admin/` but the URL has no `/admin`
  part. Everything is at `/v1/accounts`.

---

## 5. Cleanup

- [ ] **SHOULD** Remove `print()` from running code:
  - `app/consumers/schedulers/main.py:16` — this is the whole body of a job
    that runs every 15 seconds
  - `infra/local_auth.py:122`

- [ ] **NICE** `app/routers/customer/accounts.py` is an empty file (0 bytes)
  and is not included in `main.py`. Either build it or delete it.

- [ ] **NICE** Two different classes named `CustomerAccountCreated`
  (`app/events/local/main.py:7` and
  `app/events/distributed/outgoing/main.py:7`) with the same `route()`. This
  forces renamed imports in `app/consumers/entrypoints/main.py:12-15`. Same
  problem for the discrepancy/verified classes. Give them different names.

- [ ] **NICE** `InvalidPaginationCursor` is defined twice and used nowhere
  (`app/schemas/request.py:10`, `app/schemas/response.py:18`).

- [ ] **NICE** `@runtime_checkable` is on `CustomerRepository` but not on
  `CustomerAccountRepository` (`domain/repository.py:12` vs `:19`). Make them
  consistent, or write down why they differ.

- [ ] **NICE** `CustomerAccountLedger.create(entity_id=...)`
  (`domain/entities/account.py:146`) puts `entity_id` into both `account_id`
  and `operation_id`. The parameter name does not say that.

- [ ] **NICE** Possible 500 on listing: `Customer.create` takes
  `name: str`, but the column is `str | None`
  (`domain/entities/customer.py:25` vs `:51`), while
  `CustomerAccountDisplay.name` is not optional
  (`app/schemas/account.py:50`). A null name will fail serialization.

- [ ] **NICE** The `Currency` enum (`domain/enum.py:4`) is not used by the
  entity — the column is a plain `str` (`domain/entities/account.py:44`). So
  currency is only checked at the API edge, not in the model or the database.

- [ ] **NICE** Test named
  `test_deposit_and_withdrawal_of_one_entity_id_do_not_collide`
  (`tests/app/subscribers/test_payment_commands.py:114`) actually asserts that
  the keys **are** equal. The name says the opposite of the test. Rename it.

- [ ] **NICE** The `broker` fixture (`tests/conftest.py:76-84`) patches
  `publish` on a broker object that is thrown away — `build_broker()` returns a
  new object every call. The mock is never checked by anything.

---

## 6. Missing tests

- [ ] **SHOULD** Nothing tests that events are actually published.
  No test mentions `CustomerAccountCreated`, `customer-account.created`, or
  `publish`. The whole outgoing message path is unverified.

- [ ] **SHOULD** `persistence/versioned_history.py` — 322 lines, has
  `ignore_errors = true` in mypy **and** no tests. The history tables are never
  checked, even though versioning is a headline feature of the project.
  Note: you changed the upstream version default from `max(version)+1` to a
  literal `1` (`versioned_history.py:143-152`). That change is yours, not
  SQLAlchemy's, so it deserves a test.

- [ ] **NICE** Untested endpoints:
  `GET /v1/accounts/{id}/ledger/discrepancy` and
  `POST /v1/accounts/{id}/ledger/discrepancy/resolve`.

- [ ] **NICE** Untested modules: `infra/local_auth.py`,
  `infra/observability.py`, the `StaleDataError` handler in `main.py:38`.

- [ ] **NICE** No test builds `Settings()` with bad input, so config validation
  is unchecked.

---

## 7. Security, when the customer API is built

These do not matter yet because every endpoint is admin only, but they will
matter as soon as real users log in.

- [ ] **MUST (later)** `JWT_AUDIENCE` defaults to `None` (`conf.py:20`), so
  `verify_aud` is off (`infra/auth.py:38`). Any token from a trusted issuer is
  accepted, even if it was made for a different application. With Cognito this
  is a real token-reuse hole.

- [ ] **MUST (later)** There is no ownership check anywhere. Permission is by
  scope only. `principal.sub` is used just as an audit field
  (`account.py:63`, `:124`, `:297`). Nothing stops customer A from reading
  customer B's account once a customer endpoint exists.

- [ ] **SHOULD (later)** No `leeway` for clock skew, no `nbf`/`iat` required,
  no `jti` or revocation, and no `token_use` check (Cognito access tokens and
  id tokens are both accepted).

- [ ] **NICE** `PyJWKClient` has no timeout (`infra/auth.py:51`). A slow JWKS
  server will block threadpool workers.

- [ ] **NICE** The 403 message lists exactly which scopes are missing
  (`fast_deps.py:69`). Small information leak.

- [ ] **NICE** An empty string `""` inside a `jwt_issuers` scope list would
  make `startswith` match everything and turn off the scope check. Nothing
  validates that.

---

## 8. Docs

- [ ] **SHOULD** `README.md` has no instructions for running anything.
  The real commands only exist as comments in `compose.yaml:53-55` and
  `cicd/docker/Dockerfile:17-18`. It does not say that an external `backend`
  docker network with Postgres and RabbitMQ must already exist.

- [ ] **NICE** README says "ddd". The domain layer is deliberately anemic (see
  below), so this word will mislead people. "layered" or "clean-ish" is more
  honest.

- [ ] **NICE** Add `.env.example` so people know which variables are needed.

---

## Decisions made on purpose — do not "fix" these

- **Anemic domain models.** The entities are SQLAlchemy models and business
  rules live in the consumer, the routers and in SQL. This is a deliberate
  choice to avoid writing a mapping layer between domain objects and the
  database. Known cost: when the customer write path is built, the account
  status check and the balance check will have to be duplicated or moved.
  Decide then, not now.

- **"Outbox" in the README is correct.** There is no table called `outbox`, but
  the pattern is there: the router writes the account and enqueues the event on
  the same database connection and the same transaction (`deps.py:27-30`,
  `app/routers/admin/account.py:84-90`), and the pgqueuer worker publishes it
  later. Using the pgqueuer job table as the outbox table is a good version of
  this pattern, not a weaker one — retries, backoff and dedupe come for free.

- **`filterwarnings = ["error"]`** with `>=` version ranges. This looks risky
  but you always run `uv sync --locked` and you commit `uv.lock`, so versions
  do not move on their own. Keep it.

- **`Settings` reads only from the real environment**, with no `env_file`.
  This is correct 12-factor style and maps directly onto Kubernetes ConfigMaps
  and AWS Secrets Manager. The only annoyance is that you must run things
  through docker compose.

- **No CI yet.** Planned for later, together with k8s and AWS.
