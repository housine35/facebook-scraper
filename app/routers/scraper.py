from fastapi import APIRouter, Request, Form
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from app.services.facebook_scraper import scrape_facebook_post
from app.utils.utils import save_to_excel
import io
import pandas as pd

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def get_form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/scrape")
async def scrape_post(request: Request, url: str = Form(...)):
    try:
        post_data = await scrape_facebook_post(url)
        
        # Create Excel file in memory
        output = io.BytesIO()
        save_to_excel(post_data, output)

        # Return Excel as downloadable file
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=facebook_post_{post_data['post_id']}.xlsx"}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Échec du scraping : {str(e)}", "url": url}
        )