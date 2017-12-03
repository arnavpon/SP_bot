# Class that defines behavior for Bot Framework 'Activity'

import requests
import json
from random import randint
from pprint import pprint
from patient.patient import Patient
from LUIS import LUIS
from feedback import FeedbackModule

UPDATED_POSITION = None  # indicator used to prevent backwards actions in conversation flow

class Activity():

    # --- INITIALIZER ---
    def __init__(self, authenticator, post_body, position, patient=None):  # initializer
        print("\nInitializing ACTIVITY object w/ JSON data:")
        pprint(post_body)  # output JSON from bot client
        self.__authenticator = authenticator  # store the <Authentication> object
        self.__postBody = post_body  # store the POST data
        self.__conversationID = post_body['conversation']['id']  # get conversation ID (needed to construct URL)
        self.__channel = post_body.get("channelId", None)  # channel the user is accessing bot with
        self.__patient = patient  # initialize <Patient> object w/ passed-in argument
        global UPDATED_POSITION  # indicator that is referenced by the server to keep track of current flow position

        if position < 0:  # indicator that interaction is closed & user is receiving FEEDBACK
            feedback_handler = FeedbackModule(self, position)  # init w/ <Activity> instance & position in flow
            UPDATED_POSITION = feedback_handler.getPosition()  # obtain position from handler
        elif position == 0:  # INITIAL interaction - send introductory options

            body = {
                "messaging_type": "RESPONSE",
                "recipient":{
                    "id": post_body['from']['id']
                },
                "message": {
                    "text": "hello, world!"
                }
            }

            return_url = self.getResponseURL()  # (1) get return URL
            head = self.getResponseHeader()  # (2) get OUT-going auth token for the header
            message_shell = body
            pprint(message_shell)

            req = requests.post(return_url, data=json.dumps(message_shell), headers=head)  # send response
            print("Sent response to URL: [{}] with code {}".format(return_url, req.status_code))
            if self.__patient:  # check if patient exists
                self.__patient.removeBlock(
                    self.__conversationID)  # remove block AFTER sending msg to prep for next query
            if req.status_code != 200:  # check for errors on delivery
                print("[Delivery Error] Msg: {}".format(req.json()))

            # categories = Patient.getAllCategories()  # fetch set of all categories
            #
            # # Create a list of sub-actions (for the ShowCard) by category:
            # show_actions = [self.createAction(cat.title(), option_key='intro_1', option_value={"category": cat})
            #                 for cat in categories]  # set the selection option -> the category name
            #
            # body = [
            #     self.createTextBlock("Welcome to the Interview Bot!", size="large", weight="bolder"),
            #     self.createTextBlock("Please select an option to get started:")
            # ]
            # actions = [
            #     self.createAction("Choose a random case", option_key="intro_1", option_value={"option": 0}),
            #     self.createAction("Select case by specialty", type=1,
            #                           body=[self.createTextBlock("Choose a specialty:")],
            #                           actions=show_actions)
            # ]
            # self.createMessage(body=body, actions=actions)
            UPDATED_POSITION = position + 1  # update the position to prevent out-of-flow actions
        else:  # get the activity type, use it to handle what methods are performed
            self.activityType = post_body['type']
            if self.activityType == "message":  # POST a response to the message to the designated URL
                if self.__postBody.get('text', None) and (self.__patient is not None):  # user sent TEXT message
                    received_text = self.__postBody.get('text')
                    if received_text.strip().upper() == "END ENCOUNTER":  # close the encounter
                        feedback_handler = FeedbackModule(self, 0)  # init Feedback Module object to handle next step
                        UPDATED_POSITION = feedback_handler.getPosition()  # NEGATIVE position => encounter was CLOSED
                    else:  # question for the bot
                        _ = LUIS(received_text, self)  # pass the user's input -> a LUIS object

                elif self.__postBody.get("value", None) is not None:  # user selected a card (from initial sequence)
                    received_value = self.__postBody.get('value')  # obtain the option number that was sel
                    if type(received_value) is str:  # FB messenger passes data as JSON (not as a dict!)
                        received_value = json.loads(received_value)  # convert JSON -> dict

                    if ("intro_1" in received_value) and (position == 1):  # 1st intro option
                        received_value = received_value["intro_1"]  # get the dict inside
                        if "option" in received_value:  # user selected RANDOM CASE option
                            pts = Patient.getAllPatients()
                            rand_pt = randint(0, (pts.count() - 1))  # generate random # from 0 to (# of patients - 1)
                            self.__patient = Patient(pts[rand_pt]['_id'])  # randomly select one of our SPs & initialize
                            self.renderIntroductoryMessage()
                        elif "category" in received_value:  # user selected a CATEGORY (specialty)
                            cat = received_value['category']  # get the selected category name
                            ccs_for_cat = Patient.getChiefComplaintsForCategory(cat)  # get CCs for specified category
                            show_actions = [self.createAction(cc.title(), option_key="intro_2",
                                                                  option_value={"id": str(_id)})
                                            for cc, _id in ccs_for_cat]  # create show card actions
                            body = [
                                self.createTextBlock("What would you like to do?")
                            ]
                            actions = [
                                self.createAction("Choose random {} case".format(cat), option_key="intro_2",
                                                      option_value={"option": 0, "category": cat}),
                                self.createAction("Select specific case by chief complaint", type=1,
                                                      body=[self.createTextBlock("Choose a chief complaint:")],
                                                      actions=show_actions)
                            ]
                            self.createMessage(body=body, actions=actions)  # present 2 new options to user via card
                        UPDATED_POSITION = 2  # move to next position in flow
                    elif ("intro_2" in received_value) and (position == 2):  # user selected an option from card #2
                        received_value = received_value["intro_2"]  # obtain the nested dict
                        if "option" in received_value:  # user chose random case for selected specialty
                            pts = Patient.getPatientsForCategory(received_value["category"])  # ids for cat
                            rand_pt = randint(0, (len(pts) - 1))  # generate rand num between 0 & (# of patients - 1)
                            self.__patient = Patient(pts[rand_pt])  # randomly select one of our SPs & initialize
                            self.renderIntroductoryMessage()
                        elif "id" in received_value:  # user selected a patient ID
                            print("Selected patient with id = {}".format(received_value["id"]))
                            self.__patient = Patient(received_value["id"])  # initialize the specified case
                            self.renderIntroductoryMessage()
                        UPDATED_POSITION = 3  # move to next position in flow

    def renderIntroductoryMessage(self):  # send message that introduces patient & BEGINS the encounter
        self.createMessage(text="Your patient is {}, a **{}** {}-old **{}** "
                                "complaining of **{}**".format(self.__patient.name,
                                                            self.__patient.age[0],
                                                            self.__patient.age[1],
                                                            self.__patient.gender,
                                                            self.__patient.chief_complaint))
        self.createMessage(text="*You can now begin taking the history.*  "
                                "Type **END ENCOUNTER** when you're ready to end the interview & get your score.")

    # --- ADAPTIVE CARD ELEMENTS ---
    def createButton(cls, type=0, title="", value=""):  # creates a BUTTON for hero card attachment
        # Parse the type (an integer value representing a type of button)
        if type == 0: type = "showImage"
        else: type = "openUrl"
        button = {
            'type': type, 'title': title, 'value': value
        }
        return button

    def createTextBlock(cls, text, size=None, weight=None):  # creates TEXT BLOCK for Adaptive card
        text_block = {'type': 'TextBlock', 'text': text}
        if (size):  # specific size has been defined (e.g. 'LARGE')
            text_block.update(size=size)
        if (weight):  # specific weight has been defined (e.g. 'BOLDER')
            text_block.update(weight=weight)
        return text_block

    def createAction(cls, title, type=0, **kwargs):  # creates ACTION button for Adaptive card
        action = {
            'title': title
        }
        if type == 0:  # default action type is SUBMIT
            action.update(type="Action.Submit")
            action.update(data={kwargs.get('option_key'): kwargs.get('option_value')})  # add data field for selection
        elif type == 1:  # 1 -> SHOW card
            action.update(type="Action.ShowCard")
            card = {
                "type": "AdaptiveCard",
                "actions": kwargs.get('actions')
            }
            if (kwargs.get('body', None)):  # check if showCard has a body
                card.update(body=kwargs.get('body'))  # add body -> card
            action.update(card=card)  # add the showCard to show on click
        return action

    # --- MESSAGE CREATION LOGIC ---
    def getResponseURL(self):  # uses info in POST body to construct URL to send response to
        serviceURL = self.__postBody['serviceUrl']  # get base URL to return response to
        activityID = self.__postBody['id']  # get the activityID (needed to construct URL)
        returnURL = serviceURL + "/v3/conversations/{}/activities/{}".format(self.__conversationID, activityID)
        return returnURL

    def getResponseHeader(self):  # constructs the response header (submits an Authorization header)
        head = {
            "Content-type": "application/json",
            "Authorization": 'Bearer {}'.format(self.__authenticator.authenticateOutgoingMessage())
        }
        return head

    def getMessageShell(self):  # constructs the SHELL of the message (metadata w/o text or attachments)
        messageData = {
            "type": "message",
            "locale": self.__postBody.get('locale', 'en-US'),
            "from": self.__postBody['recipient'],
            "conversation": self.__postBody['conversation'],
            "recipient": self.__postBody['from'],
            "replyToId": self.__postBody['id']
        }
        print(messageData)
        return messageData

    def addTextToMessage(self, messageShell, text):  # adds a text message to the message shell
        if (text):  # ONLY add text to message if it is NOT None
            messageShell.update(text=text)  # update shell w/ text
        return messageShell

    def addHeroCardToMessage(self, messageShell, **kwargs):  # adds BUTTONS to the message being constructed
        # 'buttons': an ARRAY of DICTS (keys = TYPE, TITLE, & VALUE) | see bot_framework documentation
        buttons = kwargs.get('buttons', [])  # these buttons are already formatted properly by the class method
        if (len(buttons) > 0):  # make sure there is at least 1 button before creating an attachment
            content = {"buttons": buttons}
            if kwargs.get('title', None): content.update(title=kwargs.get('title'))
            if kwargs.get('subtitle', None): content.update(subtitle=kwargs.get('subtitle'))
            if kwargs.get('text', None): content.update(text=kwargs.get('text'))
            attachment = [{
                "contentType": "application/vnd.microsoft.card.hero",
                "content": content
            }]
            messageShell.update(attachments=attachment)  # update shell w/ attachments
        return messageShell

    def addAdaptiveCardToMessage(self, messageShell, **kwargs):  # adds ACTIONS to the message being constructed
        # 'buttons': an ARRAY of DICTS (keys = TYPE, TITLE, & VALUE) | see bot_framework documentation
        body = kwargs.get('body', [])  # body elements are already formatted properly by the class method
        actions = kwargs.get('actions', [])  # these actions are already formatted by class method
        if (len(actions) > 0):  # make sure there is at least 1 action before creating attachment
            attachment = [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "body": body,
                    "actions": actions
                }
            }]
            messageShell.update(attachments=attachment)  # update shell w/ attachments
        return messageShell

    def createMessage(self, **kwargs):  # function call to create message w/ any text &/or attachments
        return_url = self.getResponseURL()  # (1) get return URL
        head = self.getResponseHeader()  # (2) get OUT-going auth token for the header
        message_shell = self.getMessageShell()  # (3) construct the message outline
        message_shell = self.addTextToMessage(message_shell, kwargs.get('text', None)) # (4A) add any text
        message_shell = self.addAdaptiveCardToMessage(message_shell, body=kwargs.get('body', []),
                                                  actions=kwargs.get('actions', []))  # (4B) add adaptive card
        message_shell = self.addHeroCardToMessage(message_shell, buttons=kwargs.get('buttons', []),
                                              title=kwargs.get('card_title', []),
                                              subtitle=kwargs.get('card_subtitle', []),
                                              text=kwargs.get('card_text', []))  # (4C) add hero card
        pprint(message_shell)

        req = requests.post(return_url, data=json.dumps(message_shell), headers=head)  # send response
        print("Sent response to URL: [{}] with code {}".format(return_url, req.status_code))
        if self.__patient:  # check if patient exists
            self.__patient.removeBlock(self.__conversationID)  # remove block AFTER sending msg to prep for next query
        if req.status_code != 200:  # check for errors on delivery
            print("[Delivery Error] Msg: {}".format(req.json()))

    # ACCESSOR METHODS
    def getConversationID(self):
        return self.__conversationID

    def getPatient(self):  # accessor method for patient
        return self.__patient

    def getPostData(self):  # accessor method for post data
        return self.__postBody