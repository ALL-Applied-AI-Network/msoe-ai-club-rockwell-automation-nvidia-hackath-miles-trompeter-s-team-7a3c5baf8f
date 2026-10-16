# YOLO EXAMPLE

from ultralytics import YOLO
model = YOLO("yolo11n.pt")

results = model.train(data='data.yaml', epochs=100) #other attributes

results = model("path/to/input")

# https://docs.ultralytics.com/models/yolo11
