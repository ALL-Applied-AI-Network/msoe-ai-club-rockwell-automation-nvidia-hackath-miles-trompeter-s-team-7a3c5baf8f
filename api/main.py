"""Sample camera API."""
from pathlib import Path
from threading import Lock
from time import monotonic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from replay import CompletionTracker, sample_times
from assessments import service

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='Filling line cameras')
lock = Lock()
model = None
sessions = {}

def video_path(camera):
    if camera not in ('vial', 'tank'):
        raise HTTPException(404, 'Unknown camera')
    # The recipe timestamps are specifically for video 5.
    demo = ROOT / 'content' / ('vial_fill_video_5.mp4' if camera == 'vial' else 'tank_level_video_5.mp4')
    if demo.exists():
        return demo
    raise HTTPException(404, f'Missing video 5 {camera} recording; recipe timing requires this recording.')

@app.get('/api/cameras/{camera}/video')
def video(camera: str):
    return FileResponse(video_path(camera), media_type='video/mp4')

class Observation(BaseModel):
    session: str = Field(min_length=1, max_length=80)
    seconds: float = Field(ge=0, allow_inf_nan=False)

@app.get('/api/assessments/{run}')
def assessments(run: str):
    return service.list(run)

@app.post('/api/assessments/{job_id}/retry')
def retry_assessment(job_id: str):
    try:
        service.retry(job_id)
    except KeyError:
        raise HTTPException(404, 'Assessment not found') from None
    return {'status': 'ok'}

@app.post('/api/vial/observe')
def observe(observation: Observation):
    global model
    with lock:
        try:
            import cv2
            from ultralytics import YOLO
            if model is None:
                weights = list((ROOT / 'models/jar_crop/runs').glob('train*/weights/best.pt'))
                if not weights:
                    raise HTTPException(503, 'No trained jar-cropping checkpoint found')
                model = YOLO(str(max(weights, key=lambda p: p.stat().st_mtime)))
                if model.names != {0: 'vial'}:
                    model = None
                    raise HTTPException(503, 'Expected a single-class vial detector')
            now = monotonic()
            for key in list(sessions):
                if now - sessions[key][0] > 1800:
                    del sessions[key]
            if observation.session not in sessions and len(sessions) >= 64:
                raise HTTPException(503, 'Too many active camera viewers')
            tracker = sessions.get(observation.session, (now, CompletionTracker()))[1]
            if tracker.last_time is not None and observation.seconds < tracker.last_time:
                tracker = CompletionTracker()
            # A slow request is backlog, not a seek. Return the actual processed
            # timestamp so the client keeps draining it, even while paused.
            timestamps = sample_times(tracker.last_time, observation.seconds)
            state = tracker.snapshot()
            capture = cv2.VideoCapture(str(video_path('vial')))
            try:
                for timestamp in timestamps:
                    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                    ok, frame = capture.read()
                    if not ok:
                        raise HTTPException(422, 'Cannot read this video timestamp')
                    result = model.predict(frame, conf=0.45, imgsz=640, device='cpu', verbose=False)[0]
                    previous_count = tracker.count
                    state = tracker.update(timestamp, result.boxes.xyxyn.cpu().tolist(), frame)
                    if tracker.count != previous_count and tracker.latest:
                        # Enqueue every completion, including multiple in this batch.
                        # Network inference runs on the worker, outside the camera lock.
                        service.submit(tracker.run, tracker.latest)
            finally:
                capture.release()
            sessions[observation.session] = (monotonic(), tracker)
            state['lag_seconds'] = max(0, observation.seconds - state['seconds'])
            state['run'] = tracker.run
            return state
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, f'Jar analysis unavailable: {exc}') from exc

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
