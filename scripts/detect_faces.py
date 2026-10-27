#!/usr/bin/env python3
"""Face boxes with Apple Vision (better than OpenCV Haar on profiles, glasses, stage light).

Run with a python that has pyobjc Vision, e.g. /home/user/venv/bin/python3 with pyobjc-framework-Vision:  # example path - real one not published
  detect_faces.py out.json img1.png img2.png ...
Writes {stem: [[x, y, w, h, confidence], ...]} in pixels, top-left origin.
"""
import json, sys
from pathlib import Path
import Quartz, Vision
from Foundation import NSURL


def detect(path):
    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    W, H = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    req = Vision.VNDetectFaceRectanglesRequest.alloc().init()
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None).performRequests_error_([req], None)
    out = []
    for o in req.results() or []:
        b = o.boundingBox()
        x, y, w, h = b.origin.x * W, (1 - b.origin.y - b.size.height) * H, b.size.width * W, b.size.height * H
        out.append([round(x), round(y), round(w), round(h), round(float(o.confidence()), 2)])
    return sorted(out)


res = {Path(p).stem: detect(p) for p in sys.argv[2:]}
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
for k, v in res.items():
    print(k, len(v), v)
