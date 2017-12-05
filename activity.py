# Class that defines behavior for Bot Framework 'Activity'

import requests
import json
import re
import math
from random import randint
from pprint import pprint
from patient.patient import Patient
from LUIS import LUIS
from feedback import FeedbackModule

UPDATED_POSITION = None  # indicator used to prevent backwards actions in conversation flow

class Activity():

    # --- INITIALIZERS ---
    def __init__(self, authenticator, post_body, position, patient=None):  # initializer
        print("\nInitializing ACTIVITY object w/ JSON data:")
        pprint(post_body)  # output JSON from bot client
        self.__authenticator = authenticator  # store the <Authentication> object
        self.__postBody = post_body  # store the POST data
        self.__conversation_id = post_body['conversation']['id']  # get conversation ID (needed to construct URL)
        self.__channel_id = post_body.get("channelId", None)  # channel the user is accessing bot with
        self.__patient = patient  # initialize <Patient> object w/ passed-in argument
        self.__action_required = False  # indicator that outgoing message will contain an ACTION
        global UPDATED_POSITION  # indicator that is referenced by the server to keep track of current flow position

        if position < 0:  # indicator that interaction is closed & user is receiving FEEDBACK
            feedback_handler = FeedbackModule(self, position)  # init w/ <Activity> instance & position in flow
            UPDATED_POSITION = feedback_handler.getPosition()  # obtain position from handler
        elif position == 0:  # INITIAL interaction - send introductory options
            self.initializeBot()
        else:  # get the activity type, use it to handle what methods are performed
            self.activityType = post_body['type']
            if self.activityType == "message":  # POST a response to the message to the designated URL
                if self.__postBody.get('text', None) and (self.__patient is not None):  # user sent TEXT message
                    received_text = self.__postBody.get('text')
                    if received_text.strip().upper() == "END ENCOUNTER":  # close the encounter
                        feedback_handler = FeedbackModule(self, 0)  # init Feedback Module object to handle next step
                        UPDATED_POSITION = feedback_handler.getPosition()  # NEGATIVE position => encounter was CLOSED
                    elif received_text.strip().upper() == "RESTART":  # restart from scratch
                        self.initializeBot()  # start bot at position 0 again
                    elif re.match(r'^ERROR', received_text.strip().upper()):  # ERROR reporting
                        issue = received_text.strip()[5:]  # grab the issue
                        self.__patient.logError(self.__conversation_id, issue)  # log error -> DB
                        self.sendTextMessage(text="Issue has been reported. Thank you!")
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
                            abbrev_cat = ""  # abbreviation to display in button title
                            if cat.lower() == "internal medicine":  # map -> abbreviation so name displays fully
                                abbrev_cat = "IM"
                            elif cat.lower() == "family medicine":
                                abbrev_cat = "FM"
                            elif cat.lower() == "psychiatry":
                                abbrev_cat = "Psych"
                            elif cat.lower() == "neurology":
                                abbrev_cat = "Neuro"
                            elif cat.lower() == "pediatrics":
                                abbrev_cat = "Peds"
                            show_actions = [self.createAction(cc.title(), option_key="intro_2",
                                                                  option_value={"id": str(_id)})
                                            for cc, _id in ccs_for_cat]  # create show card actions
                            body = [
                                self.createTextBlock("Which do you prefer?")
                            ]
                            actions = [
                                self.createAction("Random {} case".format(abbrev_cat), option_key="intro_2",
                                                  option_value={"option": 0, "category": cat}),
                                self.createAction("Choose by chief complaint", type=1,
                                                  body=[self.createTextBlock("Select a chief complaint:")],
                                                  actions=show_actions)
                            ]
                            self.sendAdaptiveCardMessage(body=body, actions=actions)  # present 2 new options via card
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

    def initializeBot(self):  # renders initial (position = 0) flow for the bot
        self.__patient = None  # *clear existing patient object to start!*
        categories = Patient.getAllCategories()  # fetch set of all categories

        # Create a list of sub-actions (for the ShowCard) by category:
        show_actions = [
            self.createAction(cat.title(), option_key='intro_1', option_value={"category": cat})
            for cat in categories]  # set the selection option -> the category name

        body = [
            self.createTextBlock("Welcome to the Interview Bot!", size="large", weight="bolder"),
            self.createTextBlock("Please select an option to get started:")
        ]
        actions = [
            self.createAction("Choose random case", option_key="intro_1", option_value={"option": 0}),
            self.createAction("Select case by specialty", type=1,
                              body=[self.createTextBlock("Choose by specialty:")],
                              actions=show_actions)
        ]
        self.sendAdaptiveCardMessage(body=body, actions=actions)  # deliver card -> user
        
        global UPDATED_POSITION
        UPDATED_POSITION = 1  # update the position to prevent out-of-flow actions

    def renderIntroductoryMessage(self):  # send message that introduces patient & BEGINS the encounter
        self.sendTextMessage(text="Your patient is {}, a **{}** {}-old **{}** "
                                  "complaining of **{}**".format(self.__patient.name,
                                                                 self.__patient.age[0],
                                                                 self.__patient.age[1],
                                                                 self.__patient.gender,
                                                                 self.__patient.chief_complaint))
        self.sendTextMessage(text="*You can now begin taking the history.*\n\n"
                                  "- Type **RESTART** at any time to start a new encounter.\n"
                                  "- Type **END ENCOUNTER** when you're ready to end the interview & get your score.\n"
                                  "- Type **ERROR: ** followed by a message to report an issue.")

    # --- ADAPTIVE CARD ELEMENTS ---
    def createButton(cls, type=0, title="", value=""):  # creates a BUTTON for HERO card attachment
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
        cls.__action_required = True  # set indicator that action is required for response
        action = {
            'title': title
        }
        if type == 0:  # default action type is SUBMIT
            action.update(type="Action.Submit")
            action.update(data={kwargs.get('option_key'): kwargs.get('option_value')})  # add data (sent in response)
        elif type == 1:  # 1 -> SHOW card
            action.update(type="Action.ShowCard")
            card = {
                "type": "AdaptiveCard",
                "actions": kwargs.get('actions')
            }
            if kwargs.get('body', None):  # check if ShowCard has a body
                card.update(body=kwargs.get('body'))  # add body -> card
            action.update(card=card)  # add the showCard to show on click
        return action

    # --- MESSAGE CREATION LOGIC ---
    def routeDirectToFacebook(self):  # determines if message should be passed DIRECT to facebook (TRUE)
        if (self.__channel_id == "facebook") and self.__action_required:
            return True  # pass -> Facebook directly
        return False  # default return value

    def getResponseURL(self):  # uses info in POST body to construct URL to send response to
        if self.routeDirectToFacebook():  # Facebook messenger channel
            access_token = "EAAD7sZBOYsK4BAJt95X17v6ZCstfHi3UgUkJZCcetgVEJpH6tFN5Ju3zQ2CTXJ" \
                           "M35o8gteO17Ixk5N96gQxUIJug5IsjSozCEogiuqgKQEfWGMf9HlIABFyC7wC4cRkugwaLssad" \
                           "9AVuPFXkw6muELn9jljXmL964bqvZCvioQZDZD"  # token to access SP Bot FB page
            return "https://graph.facebook.com/v2.6/me/messages?access_token={}".format(access_token)
        else:  # all other channels
            serviceURL = self.__postBody['serviceUrl']  # get base URL to return response to
            activityID = self.__postBody['id']  # get the activityID (needed to construct URL)
            returnURL = serviceURL + "/v3/conversations/{}/activities/{}".format(self.__conversation_id, activityID)
            return returnURL

    def getResponseHeader(self):  # constructs the response header (submits an Authorization header)
        head = {
            "Content-type": "application/json"
        }
        if not self.routeDirectToFacebook():  # routing through Bot Framework - add authorization header
            head["Authorization"] = 'Bearer {}'.format(self.__authenticator.authenticateOutgoingMessage())
        return head

    def getMessageShell(self):  # constructs the SHELL of the message (metadata w/o text or attachments)
        if self.routeDirectToFacebook():  # message direct -> Facebook messenger
            message_data = {
                "messaging_type": "RESPONSE",
                "recipient": {
                    "id": self.__postBody['from']['id']
                }
            }
        else:  # (default) message going through Bot Framework
            message_data = {
                "type": "message",
                "locale": self.__postBody.get('locale', 'en-US'),
                "from": self.__postBody['recipient'],
                "conversation": self.__postBody['conversation'],
                "recipient": self.__postBody['from'],
                "replyToId": self.__postBody['id']
            }
        return message_data

    def modifyTextFormattingForFacebook(self, text):  # converts from BotFramework -> Facebook formatting
        text = self.reformatText(text, r'\*\*', '+')  # modify the ** -> a + temporarily
        text = self.reformatText(text, r'\*', '_')  # modify the * -> a _ (italic in Facebook)
        text = self.reformatText(text, r'\+', '*')  # modify the + -> * (bold in Facebook)
        return text

    def reformatText(self, text, old_markup, new_markup):  # reformats string formatting to match different protocols
        indexes = list()  # construct a list of START indexes for matches
        match_len = 0  # size of markup string
        for match in re.finditer(old_markup, text):  # find all bold markup
            indexes.append(match.span()[0])
            match_len = match.span()[1] - match.span()[0]  # find length of expression
        for i in reversed(indexes):  # REVERSE the index & modify the string from BACK -> FRONT
            text = text[:i] + new_markup + text[(i + match_len):]
        return text

    def sendTextMessage(self, text):  # sends text message
        return_url = self.getResponseURL()  # (1) get return URL
        head = self.getResponseHeader()  # (2) get OUT-going auth token for the header
        message_shell = self.getMessageShell()  # (3) construct the message outline
        if text is not None:  # ONLY add text to message if it is NOT None
            if self.__channel_id == "facebook":  # re-format bold & italic markup for Facebook Messenger
                text = self.modifyTextFormattingForFacebook(text)

            if self.routeDirectToFacebook():  # routing -> Facebook Messenger
                message_shell.update(message={"text": text})
            else:  # routing through BotFramework
                message_shell.update(text=text)  # update shell w/ text
        pprint(message_shell)
        self.deliverMessage(return_url, head, message_shell)

    def sendHeroCardMessage(self, title=None, subtitle=None, text=None, buttons=list()):  # sends HeroCard message
        # 'buttons': an ARRAY of DICTS (keys = TYPE, TITLE, & VALUE) | see bot_framework documentation
        return_url = self.getResponseURL()  # (1) get return URL
        head = self.getResponseHeader()  # (2) get OUT-going auth token for the header
        message_shell = self.getMessageShell()  # (3) construct the message outline
        if len(buttons) > 0:  # make sure there is at least 1 button before creating an attachment
            content = {"buttons": buttons}
            if title is not None: content.update(title=title)
            if subtitle is not None: content.update(subtitle=subtitle)
            if text is not None: content.update(text=text)
            attachment = [{
                "contentType": "application/vnd.microsoft.card.hero",
                "content": content
            }]
            message_shell.update(attachments=attachment)  # update shell w/ attachments
        pprint(message_shell)
        self.deliverMessage(return_url, head, message_shell)

    def sendAdaptiveCardMessage(self, actions, body=list()):  # sends an AdaptiveCard message w/ body (title) & actions
        # 'buttons': an ARRAY of DICTS (keys = TYPE, TITLE, & VALUE) | see bot_framework documentation
        return_url = self.getResponseURL()  # (1) get return URL
        head = self.getResponseHeader()  # (2) get OUT-going auth token for the header
        message_shell = self.getMessageShell()  # (3) construct the message outline
        additional_messages = list()  # list of additional messages after first to send
        if len(actions) > 0:  # make sure there is at least 1 action before creating attachment
            if self.routeDirectToFacebook():  # construct Facebook-specific card
                card_title = ""  # init as empty string
                for i, block in enumerate(body):  # body is LIST of text blocks - combine into single string
                    to_add = block['text']
                    if len(card_title) + len(to_add) + 2 >= 640:  # limit of 640 characters to Facebook messenger
                        remainder = body[i:]  # un-sent block elements go w/ next card
                        additional_messages.append({"body": remainder, "actions": actions})  # attach SAME actions
                        break  # terminate loop
                    card_title += self.modifyTextFormattingForFacebook(to_add) + "\n\n"

                buttons = list()  # initialize list of action buttons
                for action in actions:  # construct Facebook Messenger button for each action - *LIMIT 3 per template!*
                    if action['type'] == "Action.ShowCard":  # SHOW card - send options in separate cards
                        show_title = action['card']['body']  # get list of body items
                        show_actions = action['card']['actions']  # list of dropdown actions
                        for i, _ in enumerate(show_actions):  # every 3 buttons (limit), create new template card
                            empty_title = [self.createTextBlock(text="...")]
                            if i == 2:  # FIRST set of cards for ShowCard - add title
                                additional_messages.append({"body": show_title, "actions": show_actions[:3]})
                            elif (i + 1) % 3 == 0:  # another set of 3 cards
                                additional_messages.append({"body": empty_title, "actions": show_actions[(i-2):(i+1)]})
                            elif i == (len(show_actions) - 1):  # reached end of actions list
                                index = math.floor(i / 3) * 3  # get END index of previous group of 3
                                if i >= 2:  # title has already been displayed
                                    additional_messages.append({"body": empty_title, "actions": show_actions[index:]})
                                else:  # no title shown yet - include title
                                    additional_messages.append({"body": show_title, "actions": show_actions[index:]})
                    else:  # DEFAULT card type
                        button = {
                            "type": "postback",
                            "title": action['title'],
                            "payload": json.dumps(action['data'])
                        }  # payload MUST be <Str>, to send dict payload transmit as JSON (handled by BotFramework)
                        buttons.append(button)  # add button to list

                attachment = {
                    "attachment": {
                        "type": "template",
                        "payload": {
                            "template_type": "button",
                            "text": card_title,
                            "buttons": buttons
                        }
                    }
                }
                message_shell.update(message=attachment)  # update shell w/ attachments

            else:  # BotFramework message
                attachment = [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": body,
                        "actions": actions
                    }
                }]
                message_shell.update(attachments=attachment)  # update shell w/ attachments

        pprint(message_shell)
        self.deliverMessage(return_url, head, message_shell)  # send main message
        for msg in additional_messages:  # send all additional messages AFTER main message
            print("Delivering additional message [{}]...".format(msg))
            if "text" in msg:  # TEXT message
                self.sendTextMessage(msg['text'])
            else:  # CARD message
                title = msg['body'] if 'body' in msg else list()
                self.sendAdaptiveCardMessage(actions=msg['actions'], body=title)

    def deliverMessage(self, return_url, head, message_shell):  # delivers message to URL
        req = requests.post(return_url, data=json.dumps(message_shell), headers=head)  # send response
        print("Sent response to URL: [{}] with code {}".format(return_url, req.status_code))
        if self.__patient:  # check if patient exists
            self.__patient.removeBlock(self.__conversation_id)  # remove block AFTER sending msg to prep for next query
        if req.status_code != 200:  # check for errors on delivery
            print("[Delivery ERROR] Msg: {}".format(req.json()))

    # --- ACCESSOR METHODS ---
    def getConversationID(self):
        return self.__conversation_id

    def getPatient(self):  # accessor method for patient
        return self.__patient

    def getPostData(self):  # accessor method for post data
        return self.__postBody