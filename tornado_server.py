import json
import activity
from authentication import Authentication
from tornado import ioloop, web
from datetime import datetime

hostPort = 8000
CONVERSATIONS = dict()  # KEY = conversationID, VALUE = dict w/ KEYS of "position", "patient"
authenticator = Authentication()  # initialize authentication object

class MainHandler(web.RequestHandler):
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
    print("[{}] Starting HTTP server @ port {}...".format(datetime.now(), hostPort))
    app = web.Application([
        (r"/", MainHandler),
    ])
    app.listen(hostPort)  # listen @ localhost port 8000
    ioloop.IOLoop.instance().start()  # start the main event loop

