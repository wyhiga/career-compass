# Career Compass

Career Compass is an automated AI agent designed to discover, evaluate, and report on professional opportunities in the Japanese market that match specific LatAm/Spanish business profiles.

## Architecture

This pipeline runs autonomously via **GitHub Actions** and uses **Google Gemini** to process web data. It consists of three main stages:

1. **Discovery** (`discovery.py`): Searches the web for potential companies in Japan that match the strategic criteria.
2. **Evaluation** (`evaluation.py`): Performs deep web research and LinkedIn searches to evaluate the fit score of each candidate, finding key contacts and providing specific insights.
3. **Composition** (`composition.py`): Generates a comprehensive Weekly Briefing Email and updates the interactive HTML Dashboard.

## Setup & Automation

This project is fully automated. To set it up:

1. Store your secrets in GitHub:
   - `GOOGLE_API_KEY`: Your Google AI Studio API key.
   - `EMAIL_USERNAME`: Your Gmail address.
   - `EMAIL_APP_PASSWORD`: Your Gmail App Password.
2. The pipeline will automatically run every Monday at midnight (UTC) via GitHub Actions.
3. The generated email will be sent directly to your inbox.
4. The dashboard is accessible via GitHub Pages.

## Tech Stack
- Python 3.10
- Google GenAI SDK (`gemini-2.5-flash`)
- Vanilla HTML/CSS/JS (Dashboard)
- GitHub Actions (Automation)
