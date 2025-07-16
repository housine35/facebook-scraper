from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import scraper

app = FastAPI(title="Facebook Post Scraper")

# Mount templates
app.mount("/static", StaticFiles(directory="app/templates"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(scraper.router)