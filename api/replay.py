"""Track a stationary vial through fast departures and brief detection gaps."""
import base64
from uuid import uuid4


def sample_times(last_time, target, limit=8):
    """Drain a bounded batch on a fixed clock without skipping overdue frames."""
    start = 0 if last_time is None else last_time + 0.25
    return [start + i * 0.25 for i in range(limit) if start + i * 0.25 <= target]


class CompletionTracker:
    def __init__(self):
        self.run = uuid4().hex
        self.last_time = self.started = self.box = self.candidate = self.latest = None
        self.last_seen = None
        self.status = 'Waiting for a jar under the nozzle'
        self.departures = self.count = 0

    def update(self, seconds, boxes, frame):
        if self.last_time is not None and (seconds < self.last_time or seconds - self.last_time > 3):
            self.__init__()
        self.last_time = seconds
        status = 'Waiting for a jar under the nozzle'
        center = lambda b: (b[0] + b[2]) / 2
        selected = None
        if self.box is not None and boxes:
            # A conveyor step moves a vial much farther than ordinary detector
            # jitter. Match leftward motion and vertical geometry, not a tiny
            # symmetric distance gate that loses the vial mid-step.
            matches = [b for b in boxes
                       if -0.40 <= center(b) - center(self.box) <= 0.06
                       and abs(b[1] - self.box[1]) < 0.18
                       and abs(b[3] - self.box[3]) < 0.18]
            armed = self.candidate is not None and self.candidate[0] - self.started >= 1
            departing = [b for b in matches if center(b) < 0.40] if armed else []
            selected = min(departing or matches, key=lambda b: abs(center(b) - center(self.box)), default=None)
        elif self.box is None:
            under = [b for b in boxes if 0.43 <= center(b) <= 0.53]
            selected = min(under, key=lambda b: abs(center(b) - 0.48), default=None)
        if selected is None:
            if self.last_seen is None or seconds - self.last_seen > 1:
                self.started = self.box = self.candidate = None
                self.departures = 0
            elif self.box is not None:
                status = 'Holding jar track through a detection gap'
        else:
            self.last_seen = seconds
            x = center(selected)
            self.box = selected
            if 0.43 <= x <= 0.53:
                self.departures = 0
                if self.started is None:
                    self.started = seconds
                # Keep the last centered crop; the first moving frame can still
                # overlap the station but is usually blurred.
                if 0.46 <= x <= 0.51:
                    self.candidate = (seconds, self.crop(frame, selected))
                status = 'Jar at filling station'
            elif x < 0.40 and self.started is not None and self.candidate is not None:
                self.departures += 1
                status = 'Confirming jar departure'
                if self.candidate[0] - self.started >= 1:
                    self.count += 1
                    self.latest = dict(image=self.candidate[1], seconds=self.candidate[0], number=self.count)
                    self.started = self.box = self.candidate = None
                    self.departures = 0
                    status = 'Completed jar captured'
            else:
                self.departures = 0
                status = 'Tracking jar movement'
        self.status = status
        return self.snapshot()

    def snapshot(self):
        return dict(status=self.status, latest=self.latest, seconds=self.last_time or 0)

    @staticmethod
    def crop(frame, box):
        import cv2
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = box
        crop = frame[max(0, int(y1*height)):min(height, int(y2*height)), max(0, int(x1*width)):min(width, int(x2*width))]
        ok, encoded = cv2.imencode('.jpg', crop)
        if not ok:
            raise ValueError('Cannot encode vial crop')
        return 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode('ascii')
