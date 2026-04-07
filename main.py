import uvicorn
import threading
import time
import logging

from src.api.main import app
from src.channel.whatsapp_handler import router as whatsapp_router

app.include_router(whatsapp_router)

logger = logging.getLogger(__name__)


def _queue_scheduler():
    time.sleep(30)
    while True:
        try:
            from src.services.queue_fetcher import run_queue_update
            result = run_queue_update()
            if result["success"]:
                logger.info("queue_update_ok attractions=%d contexts=%d", result.get("attractions_fetched",0), result.get("contexts_updated",0))
            else:
                logger.warning("queue_update_failed reason=%s", result.get("reason"))
        except Exception as e:
            logger.error("queue_scheduler_error: %s", e)
        time.sleep(600)


if __name__ == "__main__":
    t = threading.Thread(target=_queue_scheduler, daemon=True, name="queue-scheduler")
    t.start()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
