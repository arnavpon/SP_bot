import os
from pymongo import MongoClient
from bson.objectid import ObjectId
from scope import Scope


#for k, v in os.environ.items():
#    print(k, ":", v)

#client = MongoClient('mongodb://localhost:27017/')  # connect to mongoDB @ default port of localhost

db_port = os.environ.get("MONGODB_SERVICE_PORT_MONGO")
db_host = os.environ.get("MONGODB_SERVICE_HOST")
client = MongoClient("mongodb://arnavpon:warhammeR10@{}/{}".format(db_host, db_port))  # connect to MongoDB
db = client.patients  # specify the DB to access (patients)
print("Connected to db: {} with collections = {}".format(db, db.collection_names()))

# how to handle spelling errors for input ROS objects? Possibility: if question is ID'd as pertaining to ROS,
# searches for the symptom w/ the spelling that most closely matches the input.

class Patient:  # a model for the SP that houses all historical information

    # --- CLASS METHODS ---
    @classmethod
    def getAllCategories(cls):  # get a list of all categories for which at least 1 SP script exists
        print("\nGenerating list of the available categories...")
        categories = db.ids.find(projection={"category": 1})  # get the IDs for each patient
        unique_categories = list(set(cat['category'] for cat in categories))  # filter to unique categories
        unique_categories.sort()  # sort alphabetically in ASCENDING order
        return unique_categories  # return SORTED list of unique categories

    @classmethod
    def getChiefComplaintsForCategory(cls, category):  # provides a list of all CCs for the given category
        print("\nFetching chief complaints from store & organizing by category...")
        patients = db.ids.find({"category": category}, projection={"chief_complaint": 1})  # get pts in category
        chief_complaints = list((pt['chief_complaint'][0], pt['_id']) for pt in patients) # [tuples: (CC, _id)]
        chief_complaints.sort(key=lambda x: x[0])  # sorts tuple by ASC FIRST element (CC)
        # the sort(lambda x: x[0]) passes EACH tuple in the list as 'x' to the operator, then sorts by x[0]
        return chief_complaints  # return sorted list

    @classmethod
    def getPatientsForCategory(cls, category):  # get list of SPs for the input category from Mongo
        print("\nFetching patients from store by category...")
        patients = db.ids.find({"category": category}, projection={"_id": 1})  # get the IDs for each patient
        return [pt['_id'] for pt in patients]  # return LIST of patientIDs

    @classmethod
    def getAllPatients(cls):  # get the FULL list of SPs from Mongo
        print("\nFetching patients from store...")
        return db.ids.find(projection={"_id": 1})  # return a list of all patientIDs

    @classmethod
    def disambiguate(self, doc, query):  # doc = keyword for the Mongo document, query is word to D/A
        # *** going to have issue w/ pain - if pain is in abdominal pain & chest pain, a
        # 'pain' query will match against both though it is only directed against one...
        # should we return the query or the CANONICAL form for the match? (add 'canonical' -> D/A documents)
        assert type(doc) is str and type(query) is str
        index = "name"  # default string used to index the Mongo record (depends on record type)
        if doc == "symptom":
            doc = db.symptoms
            index = "symptom"
        elif doc == "disease":
            doc = db.diseases
            index = "diagnosis"
        elif doc == "surgery":
            doc = db.surgeries
            index = "type"
        elif doc == "medication":
            doc = db.medications
        elif doc == "allergy":
            doc = db.allergies
            index = "allergen"
        elif doc == "relationship":
            doc = db.relationships
            index = "relationship"
        elif doc == "substance":
            doc = db.substances

        records = doc.find({index: {"$in": [query]}}, projection={'_id': 0, index: 1})
        equivalent_values = [query]  # *init a LIST before the set to prevent strings getting split into characters!*
        for rec in records:  # for EACH matching record...
            for element in rec[index]:  # add EACH equivalent element to the list
                equivalent_values.append(element.lower())  # APPEND the LOWERCASE value -> list
        return set(equivalent_values)  # return as a UNIQUE set

    # --- INITIALIZER ---
    def __init__(self, patientID):  # initialize w/ a reference to a DB object containing the model
        if (type(patientID) is str): patientID = ObjectId(patientID)  # if ID is not of correct type, cast it
        self.__patientID = patientID  # store ID to private property

        # Using the ID, access the Mongo DB record:
        record = db.ids.find({"_id": patientID})
        if record.count() == 1:  # returned 1 result
            self.__total_questions = 0  # tracks TOTAL number of questions user should ask - *MUST BE DEFINED FIRST!*
            self.__missed_questions = dict()  # keeps track of each missed question

            patient = record[0]  # access the patient for that record (@ the first position in the collection)
            self.name = patient['name']
            self.age = (patient['age']['value'], patient['age']['units'])  # tuple - (value, units)
            self.gender = patient['gender']
            self.chief_complaint, cc_ref = patient['chief_complaint']  # break down tuple
            self.symptoms = [Symptom(self, instance) for instance in cc_ref]  # CC array is from MOST -> LEAST recent

            # Initialize all historical components using data from the patient DB model:
            self.medical_history = [Disease(self, d) for d in patient.get('medical_history', list())]  # optional
            self.surgical_history = [Surgery(self, d) for d in patient.get('surgical_history', list())]  # optional
            self.medications = [Medication(self, d) for d in patient.get('medications', list())]  # optional
            self.allergies = [Allergy(self, d) for d in patient.get('allergies', list())]  # optional
            self.family_history = [FamilyMember(self, d) for d in patient.get('family_history', list())] # optional
            self.social_history = SocialHistory(self, patient.get('social_history'))  # social history is REQUIRED
            gyn_hx = patient.get('gynecologic_history', None)
            self.gynecologic_history = GynecologicHistory(self, gyn_hx) if gyn_hx else None # gyn history | OPTIONAL
            self.__cached_birth_index = None  # for Birth History - keeps track of current reference
            dev_hx = patient.get('developmental_history', None)
            self.developmental_history = DevelopmentalHistory(self, dev_hx) if dev_hx else None  # OPTIONAL

            # For FeedbackModule - keeps track of correct DDs & 3 differentials entered by user:
            feedback = patient.get('feedback')  # feedback is REQUIRED
            self.differentials = list((diff, None) for diff in feedback.get("differentials", list()))  # [tuple]
            self.points_of_emphasis = feedback.get("poe", list())  # [<String>]

        else:  # wrong number of records returned - raise Error & prevent initialization of object
            raise LookupError(["more than 1 record found"])

    # --- INSTANCE METHODS ---
    def getHPICount(self):  # returns the number of elements in the 'symptoms' array
        return len(self.symptoms)

    def getAllergenList(self):  # returns a LIST of STR containing all allergies
        return [a.allergen for a in self.allergies]

    def getSurgeryList(self):  # returns a LIST of STR containing all surgeries
        return [s.type for s in self.surgical_history]

    def getMedicationList(self):  # returns a LIST of STR containing all medications
        return [m.name for m in self.medications]

    def getDiagnosisList(self):  # returns a tuple containing diagnosed conditions sorted into ACTIVE vs. RESOLVED
        active = list(d.diagnosis for d in self.medical_history if d.status == Substance.STATUS_ACTIVE)
        resolved = list(d.diagnosis for d in self.medical_history if d.status == Substance.STATUS_PREVIOUS)
        return (active, resolved)

    def getFamilyHistorySummary(self, scope, members=list()):  # returns a string summarizing the family history
        if len(self.family_history) == 0:  # no family history provided
            return "Nothing that I'm aware of"
        else:  # FH was provided
            scope.switchScopeTo(Scope.FAMILY_HISTORY)  # open FH scope
            summary = ""  # initialize
            for fm in self.family_history:  # loop through all family members
                block = False
                # if 'members' is NOT empty, return FH ONLY for the specified members
                # if 'members' is empty, return FH for EVERY defined family member
                if len(members) > 0 and (fm.relationship not in members):
                    block = True

                if not block:  # check for blocker before running
                    if len(fm.conditions) == 0:  # family member has NO medical problems
                        summary += "My {} is healthy. ".format(fm.relationship)
                    else:  # family member has at least 1 medical problem
                        if (fm.cause_of_death):  # COD provided => fm is dead
                            summary += "My {} had {}. ".format(fm.relationship, ", ".join(fm.conditions))
                        else:  # no COD => fm is still alive
                            summary += "My {} has {}. ".format(fm.relationship, ", ".join(fm.conditions))
            return summary

    def getTravelHistorySummary(self, scope):  # returns a string summarizing the travel history
        if len(self.social_history.travel) == 0:  # no travel history provided
            return "No"
        else:  # travel history was provided
            scope.switchScopeTo(Scope.TRAVEL_HISTORY)  # open scope
            locations = []
            for t in self.social_history.travel:  # loop through all travel objects
                locations.append(t.location)  # store location
            return "I recently traveled to {}.".format(", ".join(locations))

    def getRecreationalDrugList(self):  # returns list of recreational drugs used by patient
        drug_list = {Substance.STATUS_ACTIVE: list(), Substance.STATUS_PREVIOUS: list()}  # init dict
        for substance in self.social_history.substances:
            if substance.name not in [Substance.ALCOHOL, Substance.TOBACCO]:
                drug_list[substance.status].append(substance.name)  # add substance to list based on status
        return drug_list

    def getBirthHistorySummary(self, scope):  # returns string summarizing the birth history
        if len(self.gynecologic_history.birth_history) == 0:  # no pregnancies
            return "I've never been pregnant"
        else:  # at least 1 pregnancy
            scope.switchScopeTo(Scope.BIRTH_HISTORY)  # open scope
            string = ""  # init
            string += "I've been pregnant {} time".format(len(self.gynecologic_history.birth_history))
            if len(self.gynecologic_history.birth_history) > 1: string += "s"  # pluralize if necessary
            string += ". "  # spacer

            for i, birth in enumerate(self.gynecologic_history.birth_history):  # give pregnancy categories
                if birth.category == Birth.DELIVERED:
                    article = ""
                elif birth.category == Birth.MISCARRIAGE:
                    article = "a"
                else:
                    article = "an"
                string += "Pregnancy {} was {} {}. ".format(i+1, article, birth.category)
            return string

    def findSymptomInScope(self, scope, match_to=None, element_array=list(), symptom=None):  # RECURSIVE method
        # uses the open scope to return the current Symptom object indicated by the scope
        # if 'match_to' argument is provided, checks for matching Symptom object in assoc. array of current Symptom
        print("\nSearching for symptom... Scope Elements = {}".format(element_array))
        if symptom: print("CURRENT Symptom = [{}]".format(symptom.symptom))

        if symptom is None:  # no symptom yet - start function @ level 1 (chief complaint symptom)
            print("No symptom yet - assigning CC -> sx")
            sx = self.symptoms[1] if scope.isScope(Scope.CHIEF_COMPLAINT_PREVIOUS) else self.symptoms[0]  # get CC
            elements = scope.getElement(return_Full=True)  # access FULL element array from scope
            if elements is None:  # no elements - Symptom object is CC
                if match_to: return self.getSymptomObjectWithName(sx, match_to, da=True)  # find matching <Symptom>
                else: return sx  # no 'match_to' argument given, return CC symptom
            else:  # AT LEAST 1 element found - run recursion
                return self.findSymptomInScope(scope, match_to, elements, sx)  # pass in new sx & element_array
        elif len(element_array) == 1:  # STOP when you reach last element in the array
            print("LAST element in array...")
            symptom = self.getSymptomObjectWithName(symptom, element_array[0])  # find the symptom in the assoc. array
            print("FINAL symptom is [{}]".format(symptom.symptom))
            if match_to: return self.getSymptomObjectWithName(symptom, match_to, da=True)  # find matching <Symptom>
            else: return symptom  # no 'match_to' argument given, return symptom
        else:  # > 1 element present in the scope
            print("> 1 element in scope...")
            top_level = element_array.pop(0)  # pop 0th index element (modifying 'element_array')
            print("Top lvl element = {}".format(top_level))
            symptom = self.getSymptomObjectWithName(symptom, top_level)  # find the symptom in the assoc. array
            print("Found symptom [{}]".format(symptom.symptom))
            return self.findSymptomInScope(scope, match_to, element_array, symptom)  # apply recursion

    def getSymptomObjectWithName(self, symptom, name, da=False):  # finds 'Symptom' obj in assoc_sx w/ the given name
        print("\nGetting Symptom obj named [{}] from symptom [{}]".format(name, symptom.symptom))
        for s in symptom.assoc_symptoms:  # access the assoc. array
            if type(s) is Symptom:  # make sure s has an HPI
                if da == True:  # disambiguation IS needed - can return None if no match found
                    da_list = self.disambiguate("symptom", s.symptom)  # D/A the symptom
                    if name in da_list:
                        return s  # return <Symptom> if name is in D/A array
                else:  # NO disambiguation needed - GUARANTEED match
                    if s.symptom == name: return s  # check name (no need for D/A b/c there is a GUARANTEED match)
        return None  # if no match is found - should NEVER be called

    def getObject(self, category, name, scope=None):  # input category/name, returns Object from an array
        print("[patient] Finding object of type [{}], w/ name [{}]...".format(category, name))
        if category == "disease":  # medical history
            for disease in self.medical_history:  # check array for match
                da = self.disambiguate("disease", disease.diagnosis.lower())  # D/A
                if name in da: return disease  # return object if match is found
        elif category == "surgery":
            for surgery in self.surgical_history:  # check array for match
                da = self.disambiguate("surgery", surgery.type.lower())  # D/A
                if name in da: return surgery  # return object if match is found
        elif category == "medication":
            for med in self.medications:  # check array for match
                da = self.disambiguate("medication", med.name.lower())  # D/A
                if name in da: return med  # return object if match is found
        elif category == "allergy":
            for allergy in self.allergies:  # check array for match
                da = self.disambiguate("allergy", allergy.allergen.lower())  # D/A
                if name in da: return allergy  # return object if match is found
        elif category == "family":
            for fm in self.family_history:  # check array for match
                da = self.disambiguate("relationship", fm.relationship.lower())  # D/A the substance
                if name in da: return fm  # return object if match is found
        elif category == "substance":
            for substance in self.social_history.substances:  # check array for match
                da = self.disambiguate("substance", substance.name.lower())  # D/A the substance
                if name in da: return substance  # return object if match is found
        elif category == "travel":
            print("travel")
            for loc in self.social_history.travel:  # check array for match
                print("[loc] {}".format(loc.location))
                if loc.location.lower() == name: return loc  # return object if match is found
        elif category == "birth":  # birth history - 'name' = maternal AGE @ time of birth
            print("[birth] Query = {}".format(name))
            try:  # check if the element is an Int in string form (to avoid messing up the switchScope method)
                index = int(name)  # attempt to case the name -> an Int
                print("Element is birth @ INDEX {}".format(name))
                return self.gynecologic_history.birth_history[index]  # return object @ given index
            except:  # failure to cast - use timeQualifier entity to resolve array index
                length = len(self.gynecologic_history.birth_history)  # max length
                if (name == "first") or (name == "1st") or (name == "earliest"):
                    scope.switchScopeTo("0")  # update element w/ FIRST array index
                    self.__cached_birth_index = 0  # set cache
                    return self.gynecologic_history.birth_history[0]
                elif (name == "last") or (name == "most recent") or (name == "latest"):
                    scope.switchScopeTo("{}".format((length - 1)))  # update element w/ LAST array index
                    self.__cached_birth_index = length - 1  # set cache
                elif (name == "next") or (name == "after"):  # wind 1 UP indicator
                    if self.__cached_birth_index is not None:  # we must have reference to previous index!
                        new = self.__cached_birth_index + 1  # increment
                        if new < length:  # less than MAX index
                            self.__cached_birth_index = new  # update cache
                            scope.switchScopeTo("{}".format(new))  # update element w/ NEXT index
                        else:
                            return None  # return no object for index error
                elif (name == "before") or (name == "previous") or (name == "prior"):  # wind 1 DOWN indicator
                    if self.__cached_birth_index is not None:  # we must have reference to previous index!
                        new = self.__cached_birth_index - 1  # decrement
                        if new >= 0:  # greater than MIN index
                            self.__cached_birth_index = new  # update cache
                            scope.switchScopeTo("{}".format(new))  # update element w/ NEXT index
                        else:
                            return None  # return no object for index error
                elif (name == "second") or (name == "2nd"):  # index 1
                    if length > 1:
                        scope.switchScopeTo("1")  # update element w/ array index
                        self.__cached_birth_index = 1  # set cache
                elif (name == "third") or (name == "3rd"):  # index 2
                    if length > 2:
                        scope.switchScopeTo("2")  # update element w/ array index
                        self.__cached_birth_index = 2  # set cache
                elif (name == "fourth") or (name == "4th"):  # index 3
                    if length > 3:
                        scope.switchScopeTo("3")  # update element w/ array index
                        self.__cached_birth_index = 3  # set cache
                elif (name == "fifth") or (name == "5th"):  # index 4
                    if length > 4:
                        scope.switchScopeTo("4")  # update element w/ array index
                        self.__cached_birth_index = 4  # set cache
                elif (name == "sixth") or (name == "6th"):  # index 5
                    if length > 5:
                        scope.switchScopeTo("5")  # update element w/ array index
                        self.__cached_birth_index = 5  # set cache

                if self.__cached_birth_index is not None:
                    return self.gynecologic_history.birth_history[self.__cached_birth_index]
        return None  # default if no match is found

    # --- FEEDBACK LOGIC ---
    def updateMissedQuestionsDict(self, object, key, value, flag=0):  # 0 == value ADDED, 1 == value ACCESSED
        # adds a list of missing ?s when historical elements are initialized; removes ?s when elements are accessed
        cls = type(object)  # get the Object's class
        outer_key = ""  # used to enter MQ dict
        if cls is Symptom:
            outer_key = "symptom"
        elif cls is str:  # <String> -> ROS logic (associated symptoms + pertinent negatives)
            outer_key = "ROS"
        elif cls is Disease:
            outer_key = "disease"
        elif cls is Surgery:
            outer_key = "surgery"
        elif cls is Medication:
            outer_key = "med"
        elif cls is Allergy:
            outer_key = "allergy"
        elif cls is FamilyMember:
            outer_key = "fm"
        elif cls is SocialHistory:
            outer_key = "social"
        elif cls is Substance:
            outer_key = "substance"
        elif cls is Travel:
            outer_key = "travel"
        elif cls is SexualHistory:
            outer_key = "sexual"
        elif cls is GynecologicHistory:
            outer_key = "gynecologic"
        elif cls is Birth:
            outer_key = "birth"
        elif cls is DevelopmentalHistory:
            outer_key = "developmental"

        if flag == 0:  # item was ADDED to dict
            if outer_key not in self.__missed_questions:  # OUTER key is NOT in dict
                self.__missed_questions[outer_key] = dict()  # init w/ a nested dict
            if key not in self.__missed_questions[outer_key]:  # INNER key NOT in dict
                self.__missed_questions[outer_key][key] = set()  # init w/ a set
            if (value is not None) and (value not in self.__missed_questions[outer_key][key]):  # NEW value given
                self.__total_questions += 1  # add 1 ? to total
                self.__missed_questions[outer_key][key].add(value)  # add -> set
            elif value is None:  # NoneType value given (for singular elements)
                self.__total_questions += 1  # add 1 ? to total
        elif flag == 1:  # item was ACCESSED
            if key in self.__missed_questions[outer_key]:  # INNER key exists
                current = self.__missed_questions[outer_key][key]  # get the set
                if (value is None) and len(current) == 0:  # no value provided + set is EMPTY
                    del(self.__missed_questions[outer_key][key])  # delete the key from the dict
                elif value is not None:  # value was provided
                    if value in current:  # value is in set
                        current.remove(value)  # remove value
                        if len(current) > 0:  # items remain in set
                            self.__missed_questions[outer_key][key] = current  # update
                        else:  # no items remain in set
                            del (self.__missed_questions[outer_key][key])  # delete key from dict

    def updateMissedQuestionsForQuerySymptoms(self, current_symptom, q_symptoms):  # ROS logic
        # For each query symptom, check if it is present in the assoc_symptom or pertinent_negatives lists.
        # If a match is found, use the canonical matching symptom to update the MF dict:
        assert type(current_symptom) is Symptom and type(q_symptoms) is list  # make sure query is a LIST
        combined = current_symptom.pertinent_negatives  # create a combo array of assoc + pertinent negs
        for assoc in current_symptom.assoc_symptoms:
            combined.append(assoc.symptom if type(assoc) is Symptom else assoc)  # extract & add the symptom names
        print("Combined array: {}".format(combined))
        for query in q_symptoms:  # for each query symptom...
            for symptom in combined:  # look for a match in the combined array
                if query in self.disambiguate("symptom", symptom):  # D/A each symptom in the array INDIVIDUALLY
                    self.updateMissedQuestionsDict("ROS", current_symptom.symptom, symptom, flag=1)  # symptom ACCESSED
                    break  # stop looping for THIS query symptom

    def scoreDifferentialDiagnoses(self):  # [Feedback Module] returns score for user's entered DDs
        correct = 0
        for answer, response in self.differentials:
            answer = self.disambiguate("disease", answer.lower())  # convert -> lowercase (inputs come in capitalized!)
            print("Response = '{}'. Answer = {}".format(response, answer))
            if response.lower() in answer:  # check if answer is in D/A array
                correct += 1  # increment
        return "{}/{}".format(correct, len(self.differentials))  # return <String> response

    def scoreInterview(self):  # [Feedback Module] returns score for user's interview (?s asked / total ?s)
        print("\nScoring interview...")
        missed = 0  # how many questions were missed
        for outer_k, d in self.__missed_questions.items():
            print("OUTER key = {}".format(outer_k))
            for inner_k, val in d.items():  # get the SET from the inner dict
                print("-- INNER key = {}. Value = {}.".format(inner_k, val))
                if len(val) == 0:  # if set is EMPTY but still exists, add 1 to # of missed
                    missed += 1  # this is b/c singular history elements (e.g. social & sexual hx) use empty sets
                else:  # otherwise, add the # of items in the set -> missed
                    missed += len(val)
        print("# missed = {}. Total ?s = {}".format(missed, self.__total_questions))
        percent = float(self.__total_questions - missed) / float(self.__total_questions) * 100  # calculate percentage
        return int(round(percent, 0))  # round percentage & return as an <Int>

    def getMissedQuestions(self): # [Feedback Module] displays the ?s that the user missed
        missed = list()  # return a list of <String> values displaying the message as it should be displayed
        for outer_k, d in self.__missed_questions.items():  # iterate through missed dict
            if (outer_k == "symptom") or (outer_k == "substance"):
                resorted = dict()
                for inner_k, val in d.items():  # re-sort dict so KEY = name, VALUE = historical element
                    for v in val:  # iterate through items in each set
                        if v not in resorted:
                            resorted[v] = list()  # init
                        resorted[v].append(inner_k)
                for k, v in resorted.items():
                    missed.append("(**{}**) *{}*: {}".format(outer_k.capitalize(), k.capitalize(), ", ".join(v)))
            elif outer_k == "ROS":  # ROS logic
                for inner_k in d.keys():  # items are ALREADY grouped by symptom
                    missed.append("(**ROS**) *{}*: {}".format(inner_k.capitalize(), ", ".join(d[inner_k])))
            elif (outer_k == "disease") and len(self.__missed_questions[outer_k]) > 0:
                missed.append("Past Medical History")
            elif (outer_k == "surgery") and len(self.__missed_questions[outer_k]) > 0:
                missed.append("Past Surgical History")
            elif (outer_k == "allergy") and len(self.__missed_questions[outer_k]) > 0:
                missed.append("Allergies")
            elif outer_k == "med":
                if "name" in d.keys():  # user did not ask about medications
                    missed.append("Medications")
                elif "dose" in d.keys():  # user asked about medications but forgot DOSE
                    missed.append("Medication *Doses*")
            elif outer_k == "fm":
                if "relationship" in d.keys():  # check if any FMs were missed
                    fm = ", ".join(d["relationship"])
                    missed.append("**Family History**: {}".format(fm))
            elif outer_k == "travel":
                if "location" in d.keys():
                    missed.append("Travel History")
                elif "return date" in d.keys():
                    missed.append("*Date of return* from travel")
            else:  # default
                items = [k for k in d.keys()]
                if len(items) > 0:  # *make sure at least 1 key is found!*
                    missed.append("**{} History**: {}".format(outer_k.capitalize(), ", ".join(items)))
        return missed

    # --- SCOPE LOGIC ---
    def persistCurrentScope(self, conversation, scope):  # called by LUIS class, persists the open scope
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            db.conversations.update_one(record, {"$set": {"scope": scope}})  # update scope
        else:  # conversation does NOT already exist - insert new record
            db.conversations.insert_one({"conversation": conversation,
                                         "scope": scope})  # add conversation & scope

    def checkCurrentScope(self, conversation):  # searches for the open scope for a given conversation
        record = db.conversations.find_one({"conversation": conversation}, projection={"scope": 1})
        return record.get("scope", None) if record else None  # pass back the scope if it is found

    def removeScope(self, record):  # removes the existing scope from the DB record
        db.conversations.update_one(record, {"$unset": {"scope": None}})  # remove the 'scope' value
        print("Closed scope for conversation [{}]...".format(record["conversation"]))

    def logFeedback(self, conversation, user_input):  # stores user feedback for the converation
        print("Logging feedback for conversation [{}]...".format(conversation))
        record = db.conversations.find_one({"conversation": conversation})
        if record:
            self.removeScope(record)  # remove scope info
            feedback = record.get("feedback", "")  # grab existing feedback
            if feedback != "":  # feedback exists!
                feedback += " | "  # add separator
            feedback += user_input  # append new feedback to existing text
            db.conversations.update_one(record, {"$set": {"feedback": feedback}})  # store -> DB

    def cacheQueryForClarification(self, conversation, top_intent, entities):  # clarification SAVE logic
        # Store a COMPLETE representation of the topIntent + all entities:
        intent = {"intent": top_intent.intent, "score": top_intent.score}
        entities = [{"entity": e.entity, "type": e.type,
                     "startIndex": e.startIndex, "endIndex": e.endIndex, "score": e.score} for e in entities]
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            db.conversations.update_one(record, {"$set": {"clarification": [intent, entities]}})  # add clarification
        else:  # conversation does NOT already exist - insert new record
            db.conversations.insert_one({"conversation": conversation,
                                         "clarification": [intent, entities]})  # add conversation & clarification

    def getCacheForClarification(self, conversation):  # clarification FETCH logic
        from copy import deepcopy
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            data = deepcopy(record.get("clarification", None))  # get a copy of the data
            db.conversations.update_one(record, {"$unset": {"clarification": None}})  # *REMOVE clarification!*
            return data  # pass back the topScoring intent + all entities (2 element list)
        return None  # default - None => no clarification

    # --- FLOW CONTROL ---
    def setBlock(self, conversation):  # sets blocker to prevent new Activity from being created
        print("\n[Patient] SETTING blocker...")
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            db.conversations.update_one(record, {"$set": {"isBlocked": True}})  # set blocker
        else:  # conversation does NOT already exist - insert new record
            db.conversations.insert_one({"conversation": conversation,
                                         "isBlocked": True})  # add conversation & set blocker

    def removeBlock(self, conversation):  # removes blocker to allow Activity to be created
        print("\n[Patient] REMOVING blocker...")
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            db.conversations.update_one(record, {"$set": {"isBlocked": False}})  # remove blocker

    def isBlocked(self, conversation):  # checks if blocker is set for the given conversation
        record = db.conversations.find_one({"conversation": conversation})  # check if conversation is already in DB
        if (record):  # conversation ALREADY exists
            return record.get("isBlocked", False)  # return the current blocker value or False if key is missing
        return False  # default return value if record is not found

class Symptom:  # encapsulates a block of information for a given ROS symptom
    def __init__(self, patient, record):  # init w/ the DB record, which functions as a dict
        self.__patient = patient  # store reference to containing <Patient>

        self.symptom = record.get('symptom', None)  # creates linkage -> ROS item
        self.__onset = record.get('onset', None)  # when did symptom start <Str>
        self.__patient.updateMissedQuestionsDict(self, 'onset', self.symptom)
        self.__frequency = record.get('frequency', None)  # how often symptom occurs <Str>
        if self.__frequency:
            self.__patient.updateMissedQuestionsDict(self, 'frequency', self.symptom)
        self.__duration = record.get('duration', None)  # how long symptom lasts for <Str>
        if self.__duration:
            self.__patient.updateMissedQuestionsDict(self, 'duration', self.symptom)
        self.__precipitant = record.get('precipitant', None)  # what brings on the symptom
        self.__patient.updateMissedQuestionsDict(self, 'precipitant', self.symptom)
        self.__aggravating_factors = record.get('aggravating_factors', None)  # list of things that make symptom worse
        self.__patient.updateMissedQuestionsDict(self, 'aggravating factors', self.symptom)
        self.__alleviating_factors = record.get('alleviating_factors', None)  # list of things that make symptom better
        self.__patient.updateMissedQuestionsDict(self, 'alleviating factors', self.symptom)
        self.__progression = record.get('progression', None)  # how has symptom progressed since it started
        self.__patient.updateMissedQuestionsDict(self, 'progression', self.symptom)
        self.__severity = record.get('severity', None)  # value on scale of 1 - 10
        if self.__severity is not None:
            self.__patient.updateMissedQuestionsDict(self, 'severity', self.symptom)
        self.__quality = record.get('quality', None)  # description (tearing vs. dull/throbbing vs. sharp/stabbing)
        if self.__quality:
            self.__patient.updateMissedQuestionsDict(self, 'quality', self.symptom)
        self.__quantity = record.get('quantity', None)  # HOW MUCH of the symptom (e.g. weight loss, fever) <Str>
        if self.__quantity:
            self.__patient.updateMissedQuestionsDict(self, 'quantify', self.symptom)
        self.__location = record.get('location', None)  # (if it applies) location of pain <= utilize media object???
        if self.__location:
            self.__patient.updateMissedQuestionsDict(self, 'location', self.symptom)
        self.__radiation = record.get('radiation', None)  # does symptom radiate (String, valid string => YES, else NO)
        if self.__radiation:
            self.__patient.updateMissedQuestionsDict(self, 'radiation', self.symptom)

        self.other = record.get('other', None)  # <dict> for symptom-specific ?s (e.g. for cough, indicates sputum)

        self.pertinent_negatives = [s for s in record.get('pertinent_negatives', list())]  # pertinent neg. for ROS
        for s in self.pertinent_negatives:  # all symptoms are guaranteed to be <String> type
            self.__patient.updateMissedQuestionsDict("ROS", self.symptom, s)  # update MF w/ symptom + pertinent negs
        self.assoc_symptoms = list()  # initialize
        for s in record.get('assoc_symptoms', list()):  # array of associated symptoms
            if type(s) is str:  # simple string reference - no associated 'Symptom' record for object
                self.assoc_symptoms.append(s)
                self.__patient.updateMissedQuestionsDict("ROS", self.symptom, s)  # update MF w/ symptom + assoc. sx
            elif type(s) is dict:  # associated symptom has HPI
                s = Symptom(self.__patient, s)  # initialize object using the dict
                self.assoc_symptoms.append(s)  # add to array
                self.__patient.updateMissedQuestionsDict("ROS", self.symptom, s.symptom)  # update w/ symptom + assoc.

    @property
    def onset(self):
        self.__patient.updateMissedQuestionsDict(self, 'onset', self.symptom, flag=1)
        return self.__onset

    @property
    def frequency(self):
        self.__patient.updateMissedQuestionsDict(self, 'frequency', self.symptom, flag=1)
        return self.__frequency

    @property
    def duration(self):
        self.__patient.updateMissedQuestionsDict(self, 'duration', self.symptom, flag=1)
        return self.__duration

    @property
    def precipitant(self):
        self.__patient.updateMissedQuestionsDict(self, 'precipitant', self.symptom, flag=1)
        return self.__precipitant

    @property
    def aggravating_factors(self):
        self.__patient.updateMissedQuestionsDict(self, 'aggravating factors', self.symptom, flag=1)
        return self.__aggravating_factors

    @property
    def alleviating_factors(self):
        self.__patient.updateMissedQuestionsDict(self, 'alleviating factors', self.symptom, flag=1)
        return self.__alleviating_factors

    @property
    def progression(self):
        self.__patient.updateMissedQuestionsDict(self, 'progression', self.symptom, flag=1)
        return self.__progression

    @property
    def severity(self):
        self.__patient.updateMissedQuestionsDict(self, 'severity', self.symptom, flag=1)
        return self.__severity

    @property
    def quality(self):
        self.__patient.updateMissedQuestionsDict(self, 'quality', self.symptom, flag=1)
        return self.__quality

    @property
    def quantity(self):
        self.__patient.updateMissedQuestionsDict(self, 'quantify', self.symptom, flag=1)
        return self.__quantity

    @property
    def location(self):
        self.__patient.updateMissedQuestionsDict(self, 'location', self.symptom, flag=1)
        return self.__location

    @property
    def radiation(self):
        self.__patient.updateMissedQuestionsDict(self, 'radiation', self.symptom, flag=1)
        return self.__radiation

    # --- INSTANCE METHODS ---
    def isQueryInAssociatedSymptoms(self, query):  # checks if query symptom is an assoc. symptom of current Symptom
        associated_symptoms = self.getAssociatedSymptoms()  # get list of ALL associated symptoms from *DB RECORD*
        if query in associated_symptoms:  # check if query symptom is in list
            return True
        return False  # default return value

    def getAssociatedSymptoms(self):  # checks in Mongo 'Symptom' doc if this symptom has assoc. symptoms
        associated_symptoms = list()  # init return object
        symptom = db.symptoms.find_one({"symptom": {"$in": [self.symptom]}},
                                       projection={"_id": 0, "assoc_symptoms": 1})  # get db object for Symptom
        if symptom is not None:  # make sure object was found in DB
            if "assoc_symptoms" in symptom:  # check if symptom has any assoc. symptoms
                assoc = symptom["assoc_symptoms"]  # get list of associated symptoms
                print("Found associated symptoms = {} for Symptom [{}]".format(assoc, self.symptom))
                for assoc_s in assoc:  # iterate through list
                    da = Patient.disambiguate("symptom", assoc_s)  # disambiguate each symptom
                    for s in da:  # add each D/A -> return object
                        associated_symptoms.append(s)
        return associated_symptoms

class Disease:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__diagnosis = record.get('diagnosis', None)  # name of disease
        self.__patient.updateMissedQuestionsDict(self, 'diagnosis', self.__diagnosis)  # update MQ dict

        self.duration = record.get('duration', None)  # how long AGO patient was diagnosed w/ disease <Int>
        self.duration_units = record.get('duration_units', None)  # units (e.g. 'year'/'month') for duration
        self.status = record.get('status', None)  # active vs. resolved illness | REQUIRED
        self.treatment = record.get('treatment', None)  # <list> how disease is/was managed | OPTIONAL

    @property
    def diagnosis(self):  # if diagnosis is requested, remove element from asked
        self.__patient.updateMissedQuestionsDict(self, 'diagnosis', self.__diagnosis, flag=1)  # update MQ dict
        return self.__diagnosis

class Surgery:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__type = record.get('type', None)  # type of surgery done (REQUIRED)
        self.__patient.updateMissedQuestionsDict(self, 'type', self.__type)  # update MQ dict
        self.indication = record.get('indication', None)  # reason for surgery (REQUIRED)
        self.date = record.get('date', None)  # <string> date when surgery was done (REQUIRED)
        self.complications = record.get('complications', None)  # <string> any complicating factors

    @property
    def type(self):
        self.__patient.updateMissedQuestionsDict(self, 'type', self.__type, flag=1)  # update MQ dict
        return self.__type

class Medication:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__name = record.get('name', None)  # REQUIRED property
        self.__patient.updateMissedQuestionsDict(self, 'name', self.__name)  # update MQ dict
        self.category = record.get('category', None)  # "prescription" vs. "OTC" vs. "supplement"
        self.indication = record.get('indication', None)  # <Str> reason medication is being taken

        dose = record.get('dose', None)
        self.__dose_amount = dose.get('amount', None)  # <int> amount of specific unit that is taken
        self.dose_unit = dose.get('unit', None)  # e.g. grams, tablet, etc.
        self.dose_rate = dose.get('rate', None)  # how frequently med is taken (e.g. daily)
        self.dose_route = dose.get('route', None)  # oral vs. IM vs. IV
        self.__patient.updateMissedQuestionsDict(self, 'dose', self.__name)  # update MQ dict w/ 1 item for dose

    @property
    def name(self):
        self.__patient.updateMissedQuestionsDict(self, 'name', self.__name, flag=1)  # update MQ dict
        return self.__name

    @property
    def dose_amount(self):  # accessing dose amount is same as accessing ALL dose components
        self.__patient.updateMissedQuestionsDict(self, 'dose', self.__name, flag=1)  # update MQ dict
        return self.__dose_amount

class Allergy:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__allergen = record.get('allergen', None)  # substance that triggers reaction
        self.__patient.updateMissedQuestionsDict(self, 'allergen', self.__allergen)  # update MQ dict
        self.category = record.get('category', None)  # food vs. drug vs. seasonal
        self.__reaction = record.get('reaction', None)  # reaction when patient comes in contact w/ substance
        self.__patient.updateMissedQuestionsDict(self, 'reaction', self.__allergen)  # update MQ dict

    @property
    def allergen(self):
        self.__patient.updateMissedQuestionsDict(self, 'allergen', self.__allergen, flag=1)  # update MQ dict
        return self.__allergen

    @property
    def reaction(self):  # user should ask about reaction for EACH allergen
        self.__patient.updateMissedQuestionsDict(self, 'reaction', self.__allergen, flag=1)  # update MQ dict
        return self.__reaction

class FamilyMember:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__relationship = record.get('relationship', None)  # relationship to patient (e.g. father vs. mother)
        self.__patient.updateMissedQuestionsDict(self, 'relationship', self.__relationship)  # update MQ dict
        self.age = record.get('age', None)  # <Int> current age vs. age of death | assume units = YEAR
        self.cause_of_death = record.get('cod', None)  # if value is None, patient is still alive
        self.conditions = record.get('conditions', None)  # <list> names of diagnosed medical conditions

    @property
    def relationship(self):
        self.__patient.updateMissedQuestionsDict(self, 'relationship', self.__relationship, flag=1)  # update MQ dict
        return self.__relationship

    # --- INSTANCE METHODS ---
    def getGenderPronoun(self):  # returns the appropriate gender pronoun based on relationship
        if self.relationship in ["father", "brother", "son", "uncle", "grandfather"]:  # males
            return "he"
        else:  # females
            return "she"

class SocialHistory:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__housing = record.get('housing', None)  # current living situation | if None => homeless
        self.__patient.updateMissedQuestionsDict(self, 'housing', None)  # update MQ dict
        self.__employment = record.get('employment', None)  # current employment status | if None => unemployed
        self.__patient.updateMissedQuestionsDict(self, 'employment', None)  # update MQ dict
        self.__diet = record.get('diet', None)  # <Str> REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'diet', None)  # update MQ dict
        self.__exercise = record.get('exercise', None)  # <Str> REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'exercise', None)  # update MQ dict
        self.__sick_contacts = record.get('sick_contacts', None)  # list of strings (OPTIONAL)
        if self.__sick_contacts is not None:
            self.__patient.updateMissedQuestionsDict(self, 'sick contacts', None)  # update MQ dict
        self.__ppd = record.get('ppd', None)  # <Str> (OPTIONAL)
        if self.__ppd is not None:
            self.__patient.updateMissedQuestionsDict(self, 'PPD', None)  # update MQ dict

        self.substances = [Substance(self.__patient, s) for s in record.get('substances', list())]  # [substance] (REQ)
        self.travel = [Travel(self.__patient, t) for t in record.get('travel', list())]  # LIST of travels (OPTIONAL)
        sxh = record.get('sexual_history', None)  # OPTIONAL
        self.sexual_history = SexualHistory(self.__patient, sxh) if (sxh) else None

    @property
    def housing(self):
        self.__patient.updateMissedQuestionsDict(self, 'housing', None, flag=1)  # update MQ dict
        return self.__housing

    @property
    def employment(self):
        self.__patient.updateMissedQuestionsDict(self, 'employment', None, flag=1)  # update MQ dict
        return self.__employment

    @property
    def diet(self):
        self.__patient.updateMissedQuestionsDict(self, 'diet', None, flag=1)  # update MQ dict
        return self.__diet

    @property
    def exercise(self):
        self.__patient.updateMissedQuestionsDict(self, 'exercise', None, flag=1)  # update MQ dict
        return self.__exercise

    @property
    def sick_contacts(self):
        self.__patient.updateMissedQuestionsDict(self, 'sick contacts', None, flag=1)  # update MQ dict
        return self.__sick_contacts

    @property
    def ppd(self):
        self.__patient.updateMissedQuestionsDict(self, 'PPD', None, flag=1)  # update MQ dict
        return self.__ppd

class Substance:  # substances of abuse

    # --- CONSTANTS ---
    ALCOHOL = "alcohol"
    TOBACCO = "cigarettes"
    COCAINE = "cocaine"

    STATUS_ACTIVE = "active"
    STATUS_PREVIOUS = "previous"
    STATUS_NEVER = "never"

    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__name = record.get('name', None)  # alcohol vs. cigarettes vs. MJ
        self.__patient.updateMissedQuestionsDict(self, 'name', self.__name)
        self.status = record.get('status', None)  # never vs. previous vs. active
        self.__age_of_first_use = record.get('age_of_first_use', None)  # <int> how old when substance was first used
        if self.__age_of_first_use is not None:
            self.__patient.updateMissedQuestionsDict(self, 'age of first use', self.__name)

        amount = record.get('amount', None)  # OPTIONAL - for status = NEVER, value will not be given
        self.__amount_value = amount['value'] if amount is not None else None  # <int> amount used per instance
        self.amount_units = amount['units'] if amount is not None else None  # unit of usage (varies by substance)
        self.amount_rate = amount['rate'] if amount is not None else None  # how often substance is used (e.g. 'daily')
        if amount is not None:
            self.__patient.updateMissedQuestionsDict(self, 'amount', self.__name)  # amount_val is proxy for AMOUNT

        self.__last_use = record.get('last_use', None)  # <Str> date of last use (OPTIONAL - e.g. for tobacco)
        if self.__last_use:
            self.__patient.updateMissedQuestionsDict(self, 'time since last use', self.__name)

        duration = record.get('duration', None)  # <dict> how long substance was used for
        if (duration):  # duration was provided
            self.__duration_value = duration['value']  # <int> how long substance was used for (absolute amount)
            self.duration_units = duration['units']  # <str> units for how long substance was used for
            self.__patient.updateMissedQuestionsDict(self, 'duration of use', self.__name)  # dur_value is proxy
        else:  # no duration provided
            self.__duration_value = None  # <int> how long substance was used for (absolute amount)
            self.duration_units = None  # <str> units for how long substance was used for

    @property
    def name(self):  # when user queries for substance NAME, the STATUS is given (which is why it's not in the MQ dict)
        self.__patient.updateMissedQuestionsDict(self, 'name', self.__name, flag=1)
        return self.__name

    @property
    def age_of_first_use(self):
        self.__patient.updateMissedQuestionsDict(self, 'age of first use', self.__name, flag=1)
        return self.__age_of_first_use

    @property
    def amount_value(self):
        self.__patient.updateMissedQuestionsDict(self, 'amount', self.__name, flag=1)
        return self.__amount_value

    @property
    def last_use(self):
        self.__patient.updateMissedQuestionsDict(self, 'time since last use', self.__name, flag=1)
        return self.__last_use

    @property
    def duration_value(self):
        self.__patient.updateMissedQuestionsDict(self, 'duration of use', self.__name, flag=1)
        return self.__duration_value

class SexualHistory:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__status = record.get('status', None)  # currently vs. previously active vs. never active | REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'status', None)
        self.__partner_type = record.get('partner_type', None)  # <List> men vs. women vs. both | REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'partner type', None)
        self.__start_age = record.get('start_age', None)  # <Int> age of first coitus (OPTIONAL)
        if self.__start_age is not None:
            self.__patient.updateMissedQuestionsDict(self, 'age of first coitus', None)

        number_of_partners = record.get('number_of_partners', None)  # dict broken down by current/last year/lifetime
        self.__partners_current = number_of_partners['current']  # <Int> defaults -> 0 | REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'number of current partners', None)
        self.__partners_past_year = number_of_partners.get('past_year', None)  # <Int> optional
        if self.__partners_past_year is not None:
            self.__patient.updateMissedQuestionsDict(self, 'number of partners in past year', None)
        self.__partners_lifetime = number_of_partners.get('lifetime', None)  # <Int> optional
        if self.__partners_lifetime is not None:
            self.__patient.updateMissedQuestionsDict(self, 'number of partners over lifetime', None)

        self.__last_active = record.get('last_active', None)  # <Str> optional
        if self.__last_active:
            self.__patient.updateMissedQuestionsDict(self, 'date of last sexual activity', None)
        self.__contraception = record.get('contraception', None)  # <list> of each contraceptive method (OPTIONAL)
        if self.__contraception:
            self.__patient.updateMissedQuestionsDict(self, 'contraception', None)

    @property
    def status(self):
        self.__patient.updateMissedQuestionsDict(self, 'status', None, flag=1)
        return self.__status

    @property
    def partner_type(self):
        self.__patient.updateMissedQuestionsDict(self, 'partner type', None, flag=1)
        return self.__partner_type

    @property
    def start_age(self):
        self.__patient.updateMissedQuestionsDict(self, 'age of first coitus', None, flag=1)
        return self.__start_age

    @property
    def partners_current(self):
        self.__patient.updateMissedQuestionsDict(self, 'number of current partners', None, flag=1)
        return self.__partners_current

    @property
    def partners_past_year(self):
        self.__patient.updateMissedQuestionsDict(self, 'number of partners in past year', None, flag=1)
        return self.__partners_past_year

    @property
    def partners_lifetime(self):
        self.__patient.updateMissedQuestionsDict(self, 'number of partners over lifetime', None, flag=1)
        return self.__partners_lifetime

    @property
    def last_active(self):
        self.__patient.updateMissedQuestionsDict(self, 'date of last sexual activity', None, flag=1)
        return self.__last_active

    @property
    def contraception(self):
        self.__patient.updateMissedQuestionsDict(self, 'contraception', None, flag=1)
        return self.__contraception

class Travel:
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__location = record.get('location', None)  # location traveled to
        self.__patient.updateMissedQuestionsDict(self, 'location', self.__location)
        self.departure_date = record.get('departure_date', None)  # <Str> date of travel to location
        self.__return_date = record.get('return_date', None)  # <Str> date of return
        self.__patient.updateMissedQuestionsDict(self, 'return date', self.__location)
        self.mode = record.get('mode', None)  # <Str> sentence indicating mode of transportation (e.g. flight vs. car)

    @property
    def location(self):
        self.__patient.updateMissedQuestionsDict(self, 'location', self.__location, flag=1)
        return self.__location

    @property
    def return_date(self):  # user should ask when patient returned from the trip
        self.__patient.updateMissedQuestionsDict(self, 'return date', self.__location, flag=1)
        return self.__return_date

class GynecologicHistory:  # for OBGYN patients
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__lmp = record.get('lmp', None)  # <Str> 1st day of last menstrual period | REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'last menstrual period', None)
        self.__age_of_menarche = record.get('age_of_menarche', None)  # <Int> age of menarche (1st menses) | REQ
        self.__patient.updateMissedQuestionsDict(self, 'menarche (age)', None)
        self.__cycles = record.get('cycles', None)  # <Str> description of periods (use as is) | REQ
        self.__patient.updateMissedQuestionsDict(self, 'menstrual cycles (description)', None)
        self.__pap_smears = record.get('pap_smears', None)  # <Str> description of pap hx (use as is) | REQ
        self.__patient.updateMissedQuestionsDict(self, 'pap smears', None)
        self.birth_history = [Birth(self.__patient, b) for b in record.get('birth_hx', list())]  # [Birth] | REQ

    @property
    def lmp(self):
        self.__patient.updateMissedQuestionsDict(self, 'last menstrual period', None, flag=1)
        return self.__lmp

    @property
    def age_of_menarche(self):
        self.__patient.updateMissedQuestionsDict(self, 'menarche (age)', None, flag=1)
        return self.__age_of_menarche

    @property
    def cycles(self):
        self.__patient.updateMissedQuestionsDict(self, 'menstrual cycles (description)', None, flag=1)
        return self.__cycles

    @property
    def pap_smears(self):
        self.__patient.updateMissedQuestionsDict(self, 'pap smears', None, flag=1)
        return self.__pap_smears

class Birth:  # for Pediatric & OBGYN patients
    GENDER_BOY = "boy"
    GENDER_GIRL = "girl"

    ABORTED = "abortion"
    DELIVERED = "delivered"
    ECTOPIC = "ectopic"
    MISCARRIAGE = "miscarriage"

    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>

        self.__maternal_age = record.get('maternal_age', None)  # <Int> age of mother during pregnancy (YEARS) | REQ
        self.__patient.updateMissedQuestionsDict(self, 'maternal age', self.__maternal_age)
        self.__gestational_age = record.get('gestational_age', None)  # number of WEEKS @ birth |REQ
        self.__patient.updateMissedQuestionsDict(self, 'gestational age', self.__maternal_age)

        self.__category = record.get('category', None)  # <Str> delivered vs. ectopic vs. miscarriage | REQUIRED
        self.__patient.updateMissedQuestionsDict(self, 'category (e.g. delivered vs. ectopic)', self.__maternal_age)
        self.__birth_weight = record.get('birth_weight', None)  # <list> [lbs., oz.] | REQ
        self.__gender = Birth.GENDER_BOY if record.get('gender', None) == "male" else Birth.GENDER_GIRL  # REQUIRED
        self.__delivery_method = record.get('delivery_method', None)  # <Str> vaginal vs. C-Section | OPTIONAL
        if self.__category != Birth.DELIVERED:  # baby was NOT delivered
            self.__gender = None  # *OVERWRITE!*
            self.__birth_weight = None  # *OVERWRITE!*
            self.__delivery_method = None  # *OVERWRITE whatever value was given!*
        else:  # baby was delivered therefore delivery method, birth weight, & gender are GUARANTEED to be set
            self.__patient.updateMissedQuestionsDict(self, 'gender', self.__maternal_age)
            self.__patient.updateMissedQuestionsDict(self, 'birth weight', self.__maternal_age)
            self.__patient.updateMissedQuestionsDict(self, 'delivery method (NSVD vs. C-Section)', self.__maternal_age)

        self.__complications = record.get('complications', list())  # <list> complications during/after birth
        if len(self.__complications) > 0:  # complications exist
            self.__patient.updateMissedQuestionsDict(self, 'complications', self.__maternal_age)
        self.__indication = record.get('indication', None)  # indication for C-section | OPTIONAL
        if self.__indication is not None:
            self.__patient.updateMissedQuestionsDict(self, 'indication', self.__maternal_age)
        self.__management = record.get('management', None)  # management for non-delivered births | OPTIONAL
        if self.__management is not None:
            self.__patient.updateMissedQuestionsDict(self, 'management', self.__maternal_age)

    @property
    def maternal_age(self):
        self.__patient.updateMissedQuestionsDict(self, 'maternal age', self.__maternal_age, flag=1)
        return self.__maternal_age

    @property
    def gestational_age(self):
        self.__patient.updateMissedQuestionsDict(self, 'gestational age', self.__maternal_age, flag=1)
        return self.__gestational_age

    @property
    def birth_weight(self):
        self.__patient.updateMissedQuestionsDict(self, 'birth weight', self.__maternal_age, flag=1)
        return self.__birth_weight

    @property
    def gender(self):
        self.__patient.updateMissedQuestionsDict(self, 'gender', self.__maternal_age, flag=1)
        return self.__gender

    @property
    def category(self):
        self.__patient.updateMissedQuestionsDict(self, 'category (e.g. delivered vs. ectopic)',
                                                 self.__maternal_age, flag=1)
        return self.__category

    @property
    def delivery_method(self):
        self.__patient.updateMissedQuestionsDict(self, 'delivery method (NSVD vs. C-Section)',
                                                 self.__maternal_age, flag=1)
        return self.__delivery_method

    @property
    def complications(self):
        self.__patient.updateMissedQuestionsDict(self, 'complications', self.__maternal_age, flag=1)
        return self.__complications

    @property
    def indication(self):
        self.__patient.updateMissedQuestionsDict(self, 'indication', self.__maternal_age, flag=1)
        return self.__indication

    @property
    def management(self):
        self.__patient.updateMissedQuestionsDict(self, 'management', self.__maternal_age, flag=1)
        return self.__management

    # --- INSTANCE METHODS ---
    def getGenderPronoun(self):  # returns the appropriate gender pronoun based on relationship
        if self.__gender == Birth.GENDER_BOY:  # male
            return "he"
        else:  # female
            return "she"

class DevelopmentalHistory:  # for PEDIATRICS patients
    def __init__(self, patient, record):
        self.__patient = patient  # store reference to containing <Patient>
        birth_hx = record.get('birth_hx', None)  # patient's birth history | REQUIRED
        self.__birth_history = Birth(self.__patient, birth_hx) if birth_hx is not None else None  # <Birth> object

        self.__development = record.get('development', None)  # <Str> current developmental status | REQ
        self.__patient.updateMissedQuestionsDict(self, 'development', None)
        self.__vaccinations = record.get('vaccinations', None)  # <Str> vaccination status | REQ
        self.__patient.updateMissedQuestionsDict(self, 'vaccination status', None)
        self.__last_checkup = record.get('last_checkup', None)  # <Str> last pediatrician visit | REQ
        self.__patient.updateMissedQuestionsDict(self, 'last checkup', None)

        self.__wet_diapers = record.get('wet_diapers', None)  # number of diapers used daily | OPTIONAL
        if self.__wet_diapers:
            self.__patient.updateMissedQuestionsDict(self, 'number of wet diapers', None)

    @property
    def birth_history(self):
        self.__patient.updateMissedQuestionsDict(self, 'birth history', None, flag=1)
        return self.__birth_history

    @property
    def development(self):
        self.__patient.updateMissedQuestionsDict(self, 'development', None, flag=1)
        return self.__development

    @property
    def vaccinations(self):
        self.__patient.updateMissedQuestionsDict(self, 'vaccination status', None, flag=1)
        return self.__vaccinations

    @property
    def last_checkup(self):
        self.__patient.updateMissedQuestionsDict(self, 'last checkup', None, flag=1)
        return self.__last_checkup

    @property
    def wet_diapers(self):
        self.__patient.updateMissedQuestionsDict(self, 'number of wet diapers', None, flag=1)
        return self.__wet_diapers