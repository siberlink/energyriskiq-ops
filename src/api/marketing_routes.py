from fastapi import APIRouter
from src.alerts.templates import generate_sample_alerts, LANDING_COPY

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.get("/samples")
def get_sample_alerts():
    samples = generate_sample_alerts()
    
    return {
        "samples": samples,
        "cta": LANDING_COPY["cta"],
        "cta_upgrade": LANDING_COPY["cta_upgrade"]
    }


@router.get("/landing-copy")
def get_landing_copy():
    return {
        "hero": LANDING_COPY["hero"],
        "subhero": LANDING_COPY["subhero"],
        "bullets": LANDING_COPY["bullets"],
        "example_alerts": LANDING_COPY["example_alerts"],
        "cta": LANDING_COPY["cta"],
        "cta_upgrade": LANDING_COPY["cta_upgrade"],
        "disclaimer": LANDING_COPY["disclaimer"]
    }
