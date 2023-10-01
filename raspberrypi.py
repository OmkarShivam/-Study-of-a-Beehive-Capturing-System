from picamera2 import Picamera2
import schedule
import threading
import numpy as np
import time
import csv
import paho.mqtt.client as mqtt
import io
import json
from datetime import datetime, timedelta
from json import dumps
from random import randrange
import csv
import os
from wakeonlan import send_magic_packet
from influxdb_client import InfluxDBClient, WriteApi, Point, WriteOptions
import smbus2
import bme280
import RPi.GPIO as GPIO
from hx711 import HX711
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

#to allocate the camera
capturing = False
capturingVideo = False
online = 0
def on_message(client, userdata, msg):
    global online
    print("the message is: "+str(msg.payload.decode("utf-8")))
    online = int(msg.payload.decode("utf-8")) #online == 1 -> computer has booted and is online

def on_connect(client, userdata, flags, rc):
    client.subscribe("status")
    print("connected and subscribed")

#MQTT Address/Port
ADDRESS="localhost"
PORT = 1883

#Influx credentials
influxdb_client = InfluxDBClient(url='http://141.99.144.112:8086',
				 token='y-NOpMwuT6Z8dEuOW_q2VSya7KXipjnEXvSq62uM_nOww2T_3JqPzJ-ukrSJYOMjzgOmAHjBrl97YLUDl3qySw==',
		 org='BeeOrganisation')
write_api = influxdb_client.write_api()

#global data - contains sensor data
data = []

#define I2C Bus
bus1 = smbus2.SMBus(1) # Thermal, 1 BME
bus2 = smbus2.SMBus(2) # 2 BME

calibration_params1 = bme280.load_calibration_params(bus1, 0x76)
calibration_params2 = bme280.load_calibration_params(bus2, 0x76)
calibration_params3 = bme280.load_calibration_params(bus2, 0x77)


#Setup Scale
hx = HX711(5, 6)
hx.set_reading_format("MSB", "MSB")
hx.set_reference_unit(47.85062680375406)
hx.set_offset(328796.33333333)


#Setup camera
picam2 = Picamera2()
still_config = picam2.create_still_configuration()
video_config = picam2.create_video_configuration()
picam2.configure(still_config)
picam2.options["quality"] = 95 #for jpeg
#picam2.options["compress_level"] = 9 #for png 
picam2.start()
encoder = H264Encoder(bitrate=10000000)



#Setup MQTT
client =mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(ADDRESS,PORT)
client.loop_start()

#run any function encapulated in "run_threaded" to achieve parallelism
def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()

def reject_outliers(data, m=5):
    d = np.abs(data - np.median(data))
    mdev = np.median(d)
    s = d / (mdev if mdev else 1)
    return data[s < m]

def captureSensors():
    print("capturing")
    global data
    #one sample per sensor
    data1 = bme280.sample(bus1, 0x76, calibration_params1)
    data2 = bme280.sample(bus2, 0x76, calibration_params2)
    data3 = bme280.sample(bus2, 0x77, calibration_params3)

    currentTime = datetime.utcnow()

    averageWeight=hx.get_weight(20)        

    #append each sample to data list
    data.append(
        {
            "measurement": "temperature",
            "tags": {
                "hive": 1
            },
            "fields": {
                "temperature1": data1.temperature,
                "temperature2": data2.temperature,
                "temperature3": data3.temperature                    
            },
            "time": currentTime
        }
    )
    data.append(
        {
            "measurement": "pressure",
            "tags": {
                "hive": 1
            },
            "fields": {
                "pressure1": data1.pressure,
                "pressure2": data2.pressure,
                "pressure3": data3.pressure                    
            },
            "time": currentTime
        }
    )
    data.append(
        {
            "measurement": "humidity",
            "tags": {
                "hive": 1
            },
            "fields": {
                "humidity1": data1.humidity,
                "humidity2": data2.humidity,
                "humidity3": data3.humidity                    
            },
            "time": currentTime
        }
    )
    data.append(
        {
            "measurement": "weight",
            "tags": {
                "hive": 1
            },
            "fields": {
                "Weight": averageWeight                    
            },
            "time": currentTime
        }
    )

    print("Captured BME")
    
    

def captureVideo():
    global capturing
    global capturingVideo
    print("starting recording")
    while(capturing): #if camera is in use wait 1 second and try again
        time.sleep(0.1)
        print("waiting for camera")
    #lock camera to this recording
    capturing = True
    capturingVideo = True
    #switch to video mode
    picam2.switch_mode(video_config)
    picam2.stop()
    dt = datetime.now()
    picam2.start_recording(encoder, "images/"+str(dt)+".264")
    print("started recording")
    #record x seconds
    time.sleep(1800)
    picam2.stop_recording()
    print("stopped recording")
    #switch mode again
    picam2.start()
    picam2.switch_mode(still_config)
    #release camera
    capturingVideo =False
    capturing = False
    




def captureImage():
    print("captureimage")
    global capturing
    if(capturing): #skip taking a photo if currently recording a video
        return
    #lock camera
    capturing = True    
    print("capturing image")
    dt = datetime.now()
    imageName = str(dt)+".jpg"
    picam2.capture_file('images/'+imageName)
    print("captured image: "+imageName)
    capturing = False
    



def sendData():
    global data
    global online
    global capturingVideo
    print("sending data now")

    #wake up pc
    send_magic_packet('F0.2F.74.F9.51.AE')
    #wait for online == 1
    while (online == 0):
          print("online = "+ str(online))
          time.sleep(1)
    time.sleep(10)

    #wait for the video capturing to complete
    while(capturingVideo):
        time.sleep(1)
        print("waiting to send")


    #transfer all captured files
    for filename in os.listdir("images"):
        print(filename)
        fi=open('images/'+filename, "rb") 
        if filename.endswith('.jpg'): 
            fileContent = fi.read()
            byteArr = bytearray(fileContent)
            client.publish("Image", bytearray(filename,'utf-8')+byteArr)
        else: #transfer videos in chunks
            Chunksize=200_000_000
            while True:
                fileContent = fi.read(Chunksize)
                if not fileContent:         
                    break
                byteArr = bytearray(fileContent)
                client.publish("Image", bytearray(filename,'utf-8')+byteArr)
        fi.close()
        #delete sent files
        os.remove('images/'+filename)
        print("deleted: "+'images/'+filename)

    write_api.write(bucket="BeeBucket", record= data)

    print("transfered Data")
    data = []
    time.sleep(10)
    client.publish("Image", 0) #turn off command



    online = 0





schedule.every(10).seconds.do(run_threaded, captureSensors)
schedule.every(7).hours.do(run_threaded, sendData)
schedule.every(6).hours.do(run_threaded, captureVideo)
schedule.every(20).seconds.do(run_threaded, captureImage)


while True:
     schedule.run_pending()
     time.sleep(1)
				


		














		
