from threading import Event, Thread, Lock
from collections import deque
import argparse
import time
import socket
import cv2
import imutils
import sys

COLOR = "PINK"

working_on_the_Pi = False

if working_on_the_Pi:
    try:
        from gpiozero import LED
        from picamera.array import PiRGBArray
        from picamera import PiCamera
    except ImportError as imp:
        print("IMPORTANT  :   ARE YOU WORKING THE RASPBERRY PI ?:  ", imp)
        sys.stdout.flush()
    else:
        GREEN = LED(5)


class data_object:
    def __init__(self, *args):
        self.args = args


def gpio_blinker(led_color, loop_count):
    if working_on_the_Pi:
        if loop_count % 2 == 0:
            led_color.on()
        else:
            led_color.off()

def loop_counter(loop_number):
    loop_number += 1
    if loop_number >= 10:
        loop_number = 1
    return loop_number

def Stereoscopics(stereo_data, pi_no_pi, led_color, kill_event, show_camera, pause_event):
    stereo_data = stereo_data
    GREEN = led_color
    working_on_the_Pi = pi_no_pi
    kill_event = kill_event
    pause_event = pause_event
    show_camera = show_camera

    TCP_IP = '169.254.167.237'
    TCP_PORT = 5025
    BUFFER_SIZE = 128
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if COLOR == "RED":
        hsvLower = (0, 140, 120)
        hsvUpper = (10, 255, 255)
    elif COLOR == "PINK":
        hsvLower = (160, 80, 100)
        hsvUpper = (170, 255, 255)

    frame_width = 1008
    frame_height = 256
    framerate = 20
    resolution = (frame_width, frame_height)

    def receive_data():
        try:
            data = clientPort.recv(BUFFER_SIZE)
            # clientPort.send(data)  # SEND DATA BACK (COULD BE USED FOR STOP COMMAND)
            right_xcoord = data.decode()
            return right_xcoord
        except socket.error:
            print("[Stereo] : missed client data")

    def sendto_queue(left_xcoord, right_xcoord, start_time):
        if not pause_event.is_set():
            data = str(right_xcoord), ",", str(left_xcoord)  # , ",", str(distance)
            stereo_data.put(data)
        # fps = time.time() - start_time

    def connectClient():
        connected = False
        while not connected and not kill_event.is_set():
            try:
                print("[Stereo] Waiting for client")
                s.bind((TCP_IP, TCP_PORT))
                s.listen(1)
                clientPort, addr = s.accept()
                connected = True
                print("[Stereo] : Client connected")
                return clientPort
            except socket.error as se:
                print('[Stereo] :       No Client', se)
                sys.stdout.flush()
                time.sleep(3)
                continue
            except Exception as e:
                print('[Stereo] :       No Client' + str(e))
                sys.stdout.flush()
                time.sleep(3)
        if kill_event.is_set():
            sys.exit()

    def ProcessLoop(kill_event):
        stereo_loop_count = 1
        kill_event = kill_event
        while not kill_event.is_set():
            if pause_event.is_set():
                print("[MainProcess] : PAUSE BUTTON PRESSED")
                while pause_event.is_set():
                    time.sleep(1)

            start_time = time.time()

            if working_on_the_Pi:
                gpio_blinker(GREEN, stereo_loop_count)

            stereo_loop_count = loop_counter(stereo_loop_count)
            image = vs.read()
            image = imutils.resize(image, width=frame_width)
            blurred = cv2.GaussianBlur(image, (11, 11), 0)
            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

            mask = cv2.inRange(hsv, hsvLower, hsvUpper)


            mask = cv2.erode(mask, None, iterations=2)
            mask = cv2.dilate(mask, None, iterations=2)
            cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnts = imutils.grab_contours(cnts)

            if len(cnts) > 0:
                c = max(cnts, key=cv2.contourArea)
                M = cv2.moments(c)
                center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                centroid = (round((M["m10"] / M["m00"]), 3), round((M["m01"] / M["m00"]), 3))
                centroid = (centroid[0] * 3280 / frame_width, centroid[1] * 2464 / frame_height)

                if show_camera.is_set():
                    ((x, y), radius) = cv2.minEnclosingCircle(c)

                    if radius > 0.5:
                        cv2.circle(image, (int(x), int(y)), int(radius), (0, 255, 255), 2)
                        cv2.circle(image, center, 5, (0, 0, 255), -1)

                    cv2.imshow("Frame", image)  # mask
                    cv2.waitKey(1) & 0xFF
                try:
                    right_xcoords = receive_data()
                    right_xcoords = right_xcoords.split('<')
                    right_xcoord = right_xcoords[1]
                except IndexError as i:
                    print(right_xcoords, i)
                else:
                    try:
                        right_xcoord = int(right_xcoord)
                        left_xcoord = int(centroid[0])
                        sendto_queue(left_xcoord, right_xcoord, start_time)
                    except ValueError as val:
                        pass

                # fps = time.time() - start_time

        if kill_event.is_set():
            print("[Stereo] : closing socket connection")
            try:
                PiVideoStream(kill_event).stop()
            except PiCameraMMALError as pi:
                print(pi)
                pass
                
            clientPort.close()
            print('[Stereo] : Closing Camera...')

    class PiVideoStream:
        def __init__(self, kill_event):
            # initialize the camera and stream
            self.camera = PiCamera()
            self.camera.resolution = resolution
            self.camera.framerate = framerate
            self.rawCapture = PiRGBArray(self.camera, size=resolution)
            self.stream = self.camera.capture_continuous(self.rawCapture, format="bgr", use_video_port=True)
            # initialize the frame and the variable used to indicate
            self.frame = None
            self.stopped = False
            self.kill_event = kill_event
            time.sleep(1)

        def start(self):
            # start the thread to read frames from the video stream
            Thread(target=self.update, args=()).start()
            return self

        def update(self):
            # keep looping infinitely until the thread is stopped
            for f in self.stream:
                try:
                    # grab the frame from the stream and clear the stream in
                    # preparation for the next frame
                    self.frame = f.array
                    self.rawCapture.truncate(0)
                    if self.kill_event.is_set():
                        self.stopped = True
                    if self.stopped:
                        print('[PiVideoStream] : Closing Camera...')
                        self.stream.close()
                        self.rawCapture.close()
                        self.camera.close()
                        time.sleep(3)
                        return
                except Exception as camera_close:
                    print("This will likely catch the camera closing error ------>>   ", camera_close)

        def read(self):
            return self.frame

        def stop(self):
            self.stopped = True

    print("[Stereo] starting THREADED frames from `picamera` module...")
    sys.stdout.flush()
    clientPort = connectClient()
    try:
        vs = PiVideoStream(kill_event).start()
    except NameError as n:
        print(n)
    except Exception as e:
        print(e)
    else:
        print("[Stereo] : Initializing camera")
        sys.stdout.flush()
        time.sleep(2.0)  # < Let Video Thread startup
        ProcessLoop(kill_event)


if __name__ == "__main__":
    import multiprocessing as mp

    stereo_data = mp.Queue()
    kill_event = Event()
    show_camera = Event()
    pause_event = Event()
    show_camera.set()
    working_on_the_Pi = True
    if working_on_the_Pi:
        GREEN = LED(16)

    mp.Process(target=Stereoscopics,
               args=[stereo_data, working_on_the_Pi, GREEN, kill_event, show_camera, pause_event]).start()

    print("continuing")
    while True:
        data = stereo_data.get()
        tempData = "".join(data)
        tempData = tempData.strip("<")
        tempData = tempData.strip(">")
        tempData = tempData.split(",")
        RightXcoord = int(float(tempData[0]))
        LeftXcoord = int(float(tempData[1]))

        focalsize = 3.04e-03
        pixelsize = 1.12e-06
        baseline = 0.737

        disparity = LeftXcoord - RightXcoord
        pixel_disp = 3280 - (LeftXcoord + RightXcoord)
        print(pixel_disp)
        stereoDist = round((focalsize * baseline) / (disparity * pixelsize), 2)

        print("RightXcoord:  ", RightXcoord, "  LeftXcoord:  ", LeftXcoord, "  stereoDist:  ", stereoDist)
