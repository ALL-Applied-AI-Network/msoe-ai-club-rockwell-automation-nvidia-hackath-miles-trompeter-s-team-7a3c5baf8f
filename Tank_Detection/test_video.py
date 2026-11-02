from ultralytics import YOLO

model = YOLO(r"runs/detect/train-9/weights/best.pt")

model.predict(
    source=r"C:\Users\bmora\OneDrive\Documents\test_image.jpg",
    save=True,
    show=False
)