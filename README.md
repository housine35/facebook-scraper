# Facebook Post Scraper

A FastAPI application to scrape Facebook post data and comments, returning results as a downloadable CSV file.

## Features
- Web interface to input Facebook post URL
- Scrapes post details and comments using Playwright
- Returns data as a downloadable CSV
- Configurable proxy settings via .env file
- Docker deployment support

## Prerequisites
- Python 3.11+
- Docker (for containerized deployment)
- Playwright dependencies (install via `playwright install`)

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd facebook-scraper
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **Configure environment variables**
   Create a `.env` file in the root directory:
   ```env
   PROXY_USERNAME=your_proxy_username
   PROXY_PASSWORD=your_proxy_password
   ```

4. **Run the application**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. **Access the application**
   Open `http://localhost:8000` in your browser.

## Docker Deployment

1. **Build the Docker image**
   ```bash
   docker build -t facebook-scraper .
   ```

2. **Run the Docker container**
   ```bash
   docker run -p 8000:8000 --env-file .env facebook-scraper
   ```

3. **Access the application**
   Open `http://localhost:8000` in your browser.

## Usage
1. Enter a Facebook post URL in the web form.
2. Submit the form to scrape the post.
3. A CSV file containing the comments will be automatically downloaded.

## Notes
- Ensure the provided Facebook post URL is public and accessible.
- Proxy credentials are required for scraping (configured in `.env`).
- The application uses Playwright in headless mode for scraping.

## License
MIT License