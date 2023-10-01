import paho.mqtt.client as mqtt
import os
import time
MQTT_SERVER = "beepi.local"
PORT=1883
MQTT_PATH = "Image"
videoOpened = False
saving = False
# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.publish("status",1)
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(MQTT_PATH)
    # The callback for when a PUBLISH message is received from the server.


def on_message(client, userdata, msg):
    global f   
    global videoOpened
    global saving
    if saving:
        time.sleep(1)
        print("waiting to save")
    saving = True
    # more callbacks, etc
    # Create a file with write byte permission
    if(len(msg.payload) <30):
        print("shutting down")
        os.system("shutdown /s /t 1")
    name = str(msg.payload[:30], 'utf-8')
    print(len(name))
    name=name.replace(":", "-")
    name=name.replace(" ", "_")

    f = open(os.path.join('D:/images', name), "ab")
    f.write(msg.payload[30:])
    f.close()
    print("saved image")
    saving = False

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_SERVER, PORT)

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
client.loop_forever()