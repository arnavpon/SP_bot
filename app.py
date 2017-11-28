# lookup how to use app.py file - server instance is created by pod, how do we get requests from server?
# OR do we still need to restart our own server?
# simplify - try to create a simple runtime that displays the posted data
# (1) add a method to handle GET request & return some HTML; see if HTML is displayed when we visit site in browser!

import os
import json
import activity
from tornado import ioloop, web
from datetime import datetime
from authentication import Authentication

ip = os.environ.get("SP_BOT_SERVICE_HOST", None)  # access OpenShift environment host IP
host_port = os.environ.get("SP_BOT_SERVICE_PORT", 8080)  # access OpenShift environment PORT
CONVERSATIONS = dict()  # KEY = conversationID, VALUE = dict w/ KEYS of "position", "patient"
authenticator = Authentication()  # initialize authentication object

class MainHandler(web.RequestHandler):
    def get(self, *args, **kwargs):  # incoming GET request (test)
        print("\nParsing GET request...")
        self.write("Hello, world!")

    def post(self, *args, **kwargs):  # incoming POST request
        print("\n[{}] Received POST Request from client...".format(datetime.now()))

        # (1) Decode the POST data -> a dictionary:
        print("\nParsing POST request...")
        json_data = self.request.body  # obtain the POST body from request
        post_body = json.loads(json_data)  # convert JSON data -> dict

        # (2) Authenticate incoming message & generate a response header:
        auth_header = self.request.headers.get('Authorization', None)
        status = authenticator.authenticateIncomingMessage(auth_header, post_body.get("serviceUrl", None))  # auth
        response_header = {"Content-type": "application/json"}
        for header, value in response_header.items():  # iterate through & set response headers
            print("Head = {}. Value = {}.".format(header, value))
            self.set_header(header, value)
        if status != 200:  # authentication was UNSUCCESSFUL - terminate function
            print("Authorization failed")
            self.set_status(status, "Access Denied")  # return status code
            return  # terminate function here!

        # (3) If the request was successfully authenticated, init an <Activity> object & provide flow control:
        conversation = post_body['conversation']['id']  # cache the conversationID (identifies each UNIQUE user)
        global CONVERSATIONS  # call global dict to keep track of position/patient for each user
        if conversation not in CONVERSATIONS:  # check if conversation has been initialized
            CONVERSATIONS[conversation] = {"position": 0, "patient": None}  # initialize cache
        position = CONVERSATIONS[conversation].get("position")  # check current position in flow
        patient = CONVERSATIONS[conversation].get("patient", None)  # create a patient object to pass -> Activity
        if (patient) and (post_body.get("text", None) is not None):  # patient exists AND incoming msg is TEXT
            print("Blocker Set? {}".format(patient.isBlocked(conversation)))
            if (not patient.isBlocked(conversation)):  # blocker is NOT set - pass activity through
                patient.setBlock(conversation)  # set blocker BEFORE initializing the new activity
                current_activity = activity.Activity(authenticator, post_body, position, patient)  # init Activity
                CONVERSATIONS[conversation].update(position=activity.UPDATED_POSITION)  # update position
                CONVERSATIONS[conversation].update(patient=current_activity.getPatient())  # cache patient if it exists
        else:
            current_activity = activity.Activity(authenticator, post_body, position, patient)  # init Activity
            CONVERSATIONS[conversation].update(position=activity.UPDATED_POSITION)  # update position
            CONVERSATIONS[conversation].update(patient=current_activity.getPatient())  # cache patient if it exists


if __name__ == '__main__':
    print("[{}] Starting HTTP server @ IP {} & Port {}...".format(datetime.now(), ip, host_port))
    app = web.Application([
        (r"/", MainHandler),
    ])  # routes requests to url 'root/' to the MainHandler class
    app.listen(host_port)  # listen @ localhost port (default is 8000 unless specified in os.environ variable)
    ioloop.IOLoop.instance().start()  # start the main event loop