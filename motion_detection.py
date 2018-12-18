from flask import Flask, render_template, Response, request
from imutils.video import VideoStream
import imutils
import numpy as np
import cv2
from multiprocessing import Process
from multiprocessing import Queue
import time

app = Flask(__name__)

# run with raspberry pi usb camera or with built-in laptop webcam
pi = False

# detect with neural network or with haar cascades
network = False


def classify_frame(input_queue, output_queue):
    global first_frame
    while True:
        # check to see if there is a frame in our input queue
        if not input_queue.empty():
            frame = input_queue.get()

            # resize the frame, convert it to grayscale, and blur it
            frame = imutils.resize(frame, width=500)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            # if the first frame is None, initialize it
            if first_frame is None:
                first_frame = gray
                continue

            # compute the absolute difference between the current frame and first frame
            frame_delta = cv2.absdiff(first_frame, gray)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

            # dilate the thresholded image to fill in holes, then find contours on thresholded image
            thresh = cv2.dilate(thresh, None, iterations=2)
            detections = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            detections = imutils.grab_contours(detections)
            output_queue.put(detections)


@app.route('/')
def index():
    return render_template('index.html')


def process_frame(cam, input_queue, output_queue, detections):
    while True:
        if pi:
            frame = cam.read()
        else:
            _, frame = cam.read()

        if input_queue.empty():
            input_queue.put(frame)

        if not output_queue.empty():
            detections = output_queue.get()

        if detections is not None:
            for d in detections:
                if cv2.contourArea(d) > 500:
                    # compute the bounding box for the contour, draw it on the frame
                    (x, y, w, h) = cv2.boundingRect(d)
                    cv2.rectangle(frame, (x, y), (x + int(w * 1.4), y + int(h * 1.4)), (0, 255, 0), 2)

        _, jpeg_frame = cv2.imencode('.jpg', frame)
        bytes_frame = jpeg_frame.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytes_frame + b'\r\n\r\n')


@app.route('/video_viewer', methods=['GET', 'POST'])
def video_viewer():
    global p
    if request.method == 'POST':
        json = request.get_json()
        mode = json['mode']
        if mode == "on":
            if p is None or not p.is_alive():
                print("[INFO] starting process...")
                time.sleep(0.5)
                p = Process(target=classify_frame, args=(input_queue, output_queue,))
                p.daemon = True
                p.start()
            return Response(process_frame(video_stream, input_queue, output_queue, detections),
                            mimetype='multipart/x-mixed-replace; boundary=frame')
        else:
            p.terminate()
            return '', 204
    else:
        return Response(process_frame(video_stream, input_queue, output_queue, detections),
                        mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    input_queue = Queue(maxsize=1)
    output_queue = Queue(maxsize=1)
    first_frame = None
    detections = None
    p = None

    print("[INFO] starting video stream...")
    video_stream = VideoStream(src=0).start() if pi else cv2.VideoCapture(0)
    time.sleep(2.0)
    app.run(host='0.0.0.0')