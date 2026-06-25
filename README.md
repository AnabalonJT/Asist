# HabitTrack - Telegram-based Habit Tracking with Web Dashboard

A habit and sports tracking application that uses Telegram as the logging interface with a web dashboard for data visualization.

## Features

- 📱 Natural language activity logging via Telegram
- 🤖 LLM-powered message interpretation
- 📊 Web dashboard for data visualization
- ⏰ Configurable reminders
- 📈 Activity streak tracking
- 🔥 Calorie estimation
- 📅 Weekly summaries

## Tech Stack

- **Backend**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL with async support
- **Bot**: python-telegram-bot
- **LLM**: OpenRouter API (free models)
- **Authentication**: JWT tokens

## Setup

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 14 or higher
- Telegram Bot Token (from @BotFather)
- OpenRouter API Key

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd habittrack
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Initialize the database:
```bash
# TODO: Add alembic migration commands
```

6. Run the development server:
```bash
python -m app.main
```

The API will be available at http://localhost:8000

## Development

### Project Structure

```
habittrack/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application
│   ├── config.py         # Settings and configuration
│   ├── models/           # SQLAlchemy models
│   ├── routes/           # API route handlers
│   └── services/         # Business logic services
├── tests/                # Test suite
├── requirements.txt      # Python dependencies
└── .env.example         # Environment variables template
```

### Running Tests

```bash
pytest tests/
```

### API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT License
