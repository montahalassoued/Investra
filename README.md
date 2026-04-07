# Stockify - Multi-Agent Stock Analysis

Fast multi-agent stock analysis using CrewAI, Groq LLM, Redis cache, and FastAPI.

## Features

- 5 parallel agents (market, company, news, sentiment, recommendations)
- Groq `llama-3.3-70b-versatile` LLM (free tier)
- Redis caching with 30-day conversation history
- REST API + CLI + Python module

## Setup

```bash
# Install
git clone <repo>
cd stockify
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
pip install -e .

# Configure .env
echo "GROQ_API_KEY=your_key" > .env
echo "REDIS_HOST=host.docker.internal" >> .env

# Start Redis
docker run -d -p 6379:6379 redis:latest
```

## Usage

**CLI:**

```bash
python -m stockify AAPL MSFT GOOGL
```

**Python:**

```python
from stockify.crew import run_crew
report = run_crew(['AAPL', 'MSFT'])
```

**API:**

```bash
uvicorn app:app --reload
# http://localhost:8000
```

## API Endpoints

| Method | Endpoint            | Purpose          |
| ------ | ------------------- | ---------------- |
| POST   | `/analyze`          | Market analysis  |
| GET    | `/company/{symbol}` | Company info     |
| POST   | `/company-analysis` | Company analysis |
| POST   | `/news-sentiment`   | News & sentiment |
| POST   | `/history`          | Get history      |
| DELETE | `/history`          | Clear history    |
| GET    | `/health`           | Health check     |

## Requirements

- Python 3.10+
- Redis
- Groq API key 

## License

MIT
