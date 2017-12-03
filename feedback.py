# Feedback module, called when user closes the patient encounter

class FeedbackModule:

    # --- INSTANCE METHODS ---
    def __init__(self, activity, position):  # init w/ user's text response, SP, & position in flow
        self.__activity = activity
        self.__post_body = activity.getPostData()
        self.__patient = activity.getPatient()
        self.__position = position  # position cached against conversation, stored in server
        self.renderMessageForPosition()  # handles progress through flow

    def renderMessageForPosition(self):  # defines the server's message -> the user
        response = self.__post_body.get('text', None)
        print("[FeedbackModule] Position = {}. Response = {}.".format(self.__position, response))
        if self.__position == 0:  # INITIAL interaction
            print("\n\nScore = {}".format(self.__patient.scoreInterview())) # ***
            self.__position = -1  # set NEGATIVE position to indicate user is in feedback flow
            self.__activity.sendTextMessage(text="*Patient encounter is now **closed**.*")  # send msg
            self.__activity.sendTextMessage(text="What is your **top** differential diagnosis for my presentation?")
        elif self.__position == -1:  # (1) top differential diagnosis incoming
            if response is not None:
                self.__patient.differentials[0] = (self.__patient.differentials[0][0], response.strip())  # store DD1
                self.__activity.sendTextMessage(text="What is your **second** most likely differential diagnosis?")
                self.__position = -2
        elif self.__position == -2:  # (2) 2nd differential diagnosis incoming
            if response is not None:
                self.__patient.differentials[1] = (self.__patient.differentials[1][0], response.strip())  # store DD2
                self.__activity.sendTextMessage(text="What is your **third** most likely differential diagnosis?")
                self.__position = -3
        elif self.__position == -3:  # (3) 3rd differential diagnosis incoming - provide feedback based on inputs
            if response is not None:
                self.__patient.differentials[2] = (self.__patient.differentials[2][0], response.strip())  # store DD3
                print(self.__patient.differentials)
                score = self.__patient.scoreDifferentialDiagnoses()
                body = [
                    self.__activity.createTextBlock("### Differential Diagnosis Feedback"),
                    self.__activity.createTextBlock("Your score was **{}**".format(score)),
                    self.__activity.createTextBlock("My top 3 differentials in order are: "),
                    self.__activity.createTextBlock("**(1)** {}".format(self.__patient.differentials[0][0])),
                    self.__activity.createTextBlock("**(2)** {}".format(self.__patient.differentials[1][0])),
                    self.__activity.createTextBlock("**(3)** {}".format(self.__patient.differentials[2][0]))
                ]
                dropdown_body = [self.__activity.createTextBlock("### Key Points")]  # init dropdown text
                for poe in self.__patient.points_of_emphasis:  # display each POE
                    for i, item in enumerate(self.formatTextBlock(poe)):  # format lines so they display correctly
                        block = ""  # initialize
                        if i == 0: block += "-- "  # 1st line for each point gets a double dash
                        block += item
                        dropdown_body.append(self.__activity.createTextBlock(block))
                dropdown_btn = [self.__activity.createAction("Got It!", option_key="0", option_value=None)]
                actions = [self.__activity.createAction("OK", type=1, body=dropdown_body, actions=dropdown_btn)]
                self.__activity.sendAdaptiveCardMessage(body=body, actions=actions)  # present feedback -> user via card
                self.__position = -4
        elif self.__position == -4:  # user acknowledged Differential Diagnosis score - provide Interview Score
            received_value = self.__post_body.get('value', dict())  # make sure correct option was selected
            if "0" in received_value:  # make sure selection comes from correct button
                body = [
                    self.__activity.createTextBlock("### Interview Feedback"),
                    self.__activity.createTextBlock("You asked **{}%** of the "
                                                    "important questions!".format(self.__patient.scoreInterview()))
                ]
                missed = self.__patient.getMissedQuestions()  # list of missed questions
                if len(missed) > 0:  # user missed some questions
                    body.append(self.__activity.createTextBlock("### Missed Questions "))
                for question in missed:  # display items that were missed
                    for i, item in enumerate(self.formatTextBlock(question)):  # format the text before displaying
                        block = ""  # initialize
                        if i == 0: block += "-- "  # 1st line for each point gets a double dash
                        block += item
                        body.append(self.__activity.createTextBlock(block))
                actions = [
                    self.__activity.createAction("Sounds Good", option_key="1", option_value=None),
                ]
                self.__activity.sendAdaptiveCardMessage(body=body, actions=actions)  # present feedback via card
                self.__position = -5
        elif self.__position == -5:  # user acknowledged the Interview score - ask for feedback before close
            received_value = self.__post_body.get('value', dict())  # make sure correct option was selected
            if "1" in received_value:  # make sure selection comes from correct button
                self.__activity.createTextMessage(text="Great Job! Before you go, I'd really appreciate it if you "
                                                       "would give me some feedback on your experience today.")
                self.__activity.createTextMessage(text="Just type in your thoughts below (as many as you want), "
                                                       "and then close the client when you're finished. Thanks!")
                self.__position = -6
        else:  # user provided feedback
            if response:
                self.__patient.logFeedback(self.__activity.getConversationID(), response) # log feedback to DB
                self.__patient.removeBlock(self.__activity.getConversationID())  # remove blocker (b/c no msg is sent)!

    def formatTextBlock(self, string):  # returns a LIST of text block items using the input string
        blocks = list()
        line_cap = 47  # maximum number of characters per text block
        while len(string) > 0:  # loop until the full string has been split up
            counter = 0  # wind-back counter
            while (len(string) > line_cap) and (string[line_cap - counter] != " "):  # do NOT split words over lines
                counter += 1  # wind back by 1 character
            blocks.append(string[:(line_cap - counter)].strip())  # split line & add -> array
            string = string[(line_cap - counter):]  # truncate the portion of the string that was put in array
        return blocks

    def getPosition(self):  # returns the updated position
        return self.__position