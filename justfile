set default-list := true

# Synchronize runtime and development dependencies from the lockfile
sync:
    uv sync --locked

# Install the development environment and Git hooks
setup: sync
    uv run --locked prek install

# Check code style and formatting without changing files
lint:
    uv run --locked ruff check .
    uv run --locked ruff format --check .

# Apply code style and formatting fixes
format:
    uv run --locked ruff check . --fix
    uv run --locked ruff format .

# Check types
type-check:
    uv run --locked ty check

# Run the test suite (local, no network)
test:
    uv run --locked pytest

# Test suite with a coverage report (terminal + htmlcov/ + coverage.xml)
test-cov:
    uv run --locked pytest --cov --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml

# Run all Git hooks — the single lint gate, never ruff directly
check:
    uv run --locked prek run --all-files

# Run every quality check
all:
    just lint
    just type-check
    just test
    just check

# Scrape public ASNR sources into the local raw cache (network, rate-limited,
# resumable via cache + manifest). Sources: incident_notices (INB, done),
# reactor_outages, medical/patient/industrial_incidents (HTML),
# inspection_letters_inb (PDFs via paginated listing).
# e.g. just scrape --limit 50   (smoke)   ·   just scrape --source <name>
# (full history, hours at the robots.txt Crawl-delay — run in background)
scrape *args:
    uv run --locked python scripts/scrape.py {{args}}

# Parse the raw HTML cache into JSONL records (offline: reads data/raw only)
# e.g. just ingest --limit 50
ingest *args:
    uv run --locked python scripts/ingest.py {{args}}
