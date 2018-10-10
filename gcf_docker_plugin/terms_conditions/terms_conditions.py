import json
import sqlite3

class TermsAndConditionsDB(object):
    db_file = 'terms_conditions.db'

    def __init__(self):
        self.con = sqlite3.connect(TermsAndConditionsDB.db_file)
        with self.con:
            cursor = self.con.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS terms_conditions_accepts(user_urn TEXT PRIMARY KEY, accept_json TEXT, until_date TEXT)''')
        self.con.close()

    def find_user_accepts(self, user_urn):
        """

        :return: a pair of a date and dict mapping strings to booleans
        """
        self.con = sqlite3.connect(TermsAndConditionsDB.db_file)
        try:
            with self.con:
                cursor = self.con.cursor()
                cursor.execute('''SELECT accept_json, until_date FROM terms_conditions_accepts WHERE user_urn=?''', (user_urn,))
                for row in cursor:
                    # return (row['until_date'], json.loads(row['accept_json']))
                    return (row[1], json.loads(row[0]))
                return None
        finally:
            self.con.close()

    def register_user_accepts(self, user_urn, accepts, until):
        """

        :param user_urn: user urn (str)
        :type user_urn: str
        :param accepts: a dict which lists what the user has accepted (str -> bool)
        :type accepts: dict[str, bool]
        :param until: RFC3339 formatted date until which the accepts are valid
        :type until: str
        """
        self.con = sqlite3.connect(TermsAndConditionsDB.db_file)
        try:
            with self.con:
                cursor = self.con.cursor()
                cursor.execute('''INSERT OR REPLACE INTO terms_conditions_accepts (user_urn, accept_json, until_date) 
                                  VALUES (?, ?, ?)''', (user_urn, json.dumps(accepts), until))
                return
        finally:
            self.con.close()

    def delete_user_accepts(self, user_urn):
        """

        :param user_urn: user urn (str)
        :type user_urn: str
        """
        self.con = sqlite3.connect(TermsAndConditionsDB.db_file)
        try:
            with self.con:
                cursor = self.con.cursor()
                cursor.execute('''DELETE FROM terms_conditions_accepts WHERE user_urn=?''', (user_urn,))
                return
        finally:
            self.con.close()
