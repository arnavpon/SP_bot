import os
import json
import activity
import time
from tornado import ioloop, web
from datetime import datetime, timedelta
from authentication import Authentication

ip = os.environ.get("SP_BOT_SERVICE_HOST", None)  # access OpenShift environment host IP
host_port = os.environ.get("SP_BOT_SERVICE_PORT", 8080)  # access OpenShift environment PORT
CONVERSATIONS = dict()  # KEY = conversationID, VALUE = dict w/ KEYS of "position", "patient"
authenticator = Authentication()  # initialize authentication object

class MainHandler(web.RequestHandler):
    def get(self, *args, **kwargs):  # incoming GET request (test)
        print("\nParsing GET request...")
        from pymongo import MongoClient
        client = MongoClient("mongodb://arnavpon:warhammeR10@mongodb/patients")  # connect to remote MongoDB
        db = client.patients  # specify the DATABASE to access (patients)

        # Erase any conversation in the server cache older than 24 hours:
        expiration = datetime.now() - timedelta(minutes=1)  # amend to 24 hours after testing ***
        self.write("Current time = {}<br>".format(datetime.now()))
        self.write("Expiration threshold = {}<br>".format(expiration))
        for conversation, logs in CONVERSATIONS.items():
            print("Conversation: {}".format(conversation))
            if 'timestamp' in logs:  # access timestamp
                print("Timestamp: {}".format(logs['timestamp']))
                if logs['timestamp'] < expiration:  # timestamp is more than 24 hours old
                    print("conversation has expired! deleting...")
                    del(CONVERSATIONS[conversation])  # remove item from conversations cache
        client.close()

        # will log survive when we push next?

    def post(self, *args, **kwargs):  # incoming POST request
        print("\n[{}] Received POST Request from client...".format(datetime.now()))

        # (1) Decode the POST data -> a dictionary:
        print("\nParsing POST request...")
        json_data = self.request.body.decode('utf-8')  # obtain POST body from request, decode from bytes -> Str
        post_body = json.loads(json_data)  # convert JSON data -> dict

        # (2) Authenticate incoming message & generate a response header:
        auth_header = self.request.headers.get('Authorization', None)
        service_url = post_body.get("serviceUrl", None)
        channel_id = post_body.get("channelId", None)
        status = authenticator.authenticateIncomingMessage(auth_header, service_url, channel_id)  # authenticate req
        while status == 000:  # immature token
            time.sleep(0.05)  # brief delay before attempting to decode token again
            status = authenticator.authenticateIncomingMessage(auth_header, service_url, channel_id)
        self.set_header("Content-type", "application/json")
        if status != 200:  # authentication was UNSUCCESSFUL - terminate function
            print("Authorization failed")
            self.set_status(status, "Access Denied")  # return status code
            return  # terminate function here!

        # (3) If the request was successfully authenticated, init an <Activity> object & provide flow control:
        conversation = post_body['conversation']['id']  # cache the conversationID (identifies each UNIQUE user)
        print("\nConversation ID = {}".format(conversation))
        global CONVERSATIONS  # call global dict to keep track of position/patient for each user
        if conversation not in CONVERSATIONS:  # check if conversation has been initialized
            print("NEW conversation - initializing in CONVERSATIONS cache...")
            CONVERSATIONS[conversation] = {"position": 0, "patient": None}  # initialize cache
        position = CONVERSATIONS[conversation].get("position")  # check current position in flow
        print("Current position in conversation = [{}]".format(position))
        patient = CONVERSATIONS[conversation].get("patient", None)  # get patient object to pass -> Activity
        if (patient) and (post_body.get("text", None) is not None):  # patient exists AND incoming msg is TEXT
            print("Blocker Set? {}".format(patient.isBlocked(conversation)))
            if not patient.isBlocked(conversation):  # blocker is NOT set - pass activity through
                patient.setBlock(conversation)  # set blocker BEFORE initializing the new activity
                current_activity = activity.Activity(authenticator, post_body, position, patient)  # init Activity
                CONVERSATIONS[conversation].update(position=activity.UPDATED_POSITION)  # update position
                CONVERSATIONS[conversation].update(patient=current_activity.getPatient())  # cache patient if it exists
                CONVERSATIONS[conversation].update(timestamp=datetime.now())  # log current time of interaction
        else:  # initialization flow
            current_activity = activity.Activity(authenticator, post_body, position, patient)  # init Activity
            CONVERSATIONS[conversation].update(position=activity.UPDATED_POSITION)  # update position
            CONVERSATIONS[conversation].update(patient=current_activity.getPatient())  # cache patient if it exists
            CONVERSATIONS[conversation].update(timestamp=datetime.now())  # log current time of interaction


if __name__ == '__main__':
    print("[{}] Starting HTTP server @ IP {} & Port {}...".format(datetime.now(), ip, host_port))
    app = web.Application([
        (r"/", MainHandler),
    ])  # routes requests to the root url '/' -> the MainHandler class
    app.listen(host_port)  # listen @ localhost port (default is 8000 unless specified in os.environ variable)
    ioloop.IOLoop.instance().start()  # start the main event loop