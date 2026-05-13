import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
router = APIRouter()

SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly']


class CalendarEvent(BaseModel):
    id: str
    title: str
    start: str
    end: str
    url: str | None = None
    location: str | None = None
    description: str | None = None


def get_calendar_service():
    creds_path = settings.GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON
    if not creds_path:
        raise HTTPException(
            status_code=503,
            detail="Google Calendar service account not configured"
        )
    credentials = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


@router.get("/calendar/events")
async def calendar_events(
    calendar_id: str = Query(...),
    time_min: str = Query(...),
    time_max: str = Query(...),
) -> list[CalendarEvent]:
    try:
        service = get_calendar_service()
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=2500,
        ).execute()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Service account key file not found"
        )
    except Exception as e:
        logger.error(f"Google Calendar API error: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch calendar events"
        )

    items = result.get('items', [])
    timezone = result.get('timeZone', '')
    events = []
    for item in items:
        url = item.get('htmlLink')
        if url and timezone:
            url = f"{url}&ctz={timezone}"
        events.append(CalendarEvent(
            id=item['id'],
            title=item.get('summary', ''),
            start=item['start'].get('dateTime') or item['start'].get('date', ''),
            end=item['end'].get('dateTime') or item['end'].get('date', ''),
            url=url,
            location=item.get('location'),
            description=item.get('description'),
        ))
    return events
