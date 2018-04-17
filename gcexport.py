#!/usr/bin/python

from urllib import urlencode
from getpass import getpass
from os.path import isdir
from os import mkdir
from urllib import urlencode
import pandas as pd
import bleach
import MySQLdb as mysql
import unicodedata
import urllib2, cookielib, json


import urllib, urllib2, cookielib, json, re
#Login credentials

script_version = '1.5.0'
activities_directory = './garmin_connect_export'
username = 'EMAIL'
password = 'PASSWORD'

#Init cookie and connection
cookie_jar = cookielib.CookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))


# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers={}):
    request = urllib2.Request(url)
    request.add_header('User-Agent',
                       'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1337 Safari/537.36')  # Tell Garmin we're some supported browser.
    for header_key, header_value in headers.iteritems():
        request.add_header(header_key, header_value)
    if post:
        post = urlencode(post)  # Convert dictionary to POST parameter string.
    response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    # N.B. urllib2 will follow any 302 redirects. Also, the "open" call above may throw a urllib2.HTTPError which is checked for below.
    if response.getcode() != 200:
        raise Exception('Bad return code (' + response.getcode() + ') for: ' + url)

    return response.read()


print 'Connecting to Garmin Connect...'

#Get the username and password from the args defaults
username = username if username else raw_input('Username: ')
password = password if password else getpass()


# Maximum number of activities you can request at once.
# Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'url_gc_search'
# the limit is not known (I have less than 1000 activities and could get them all in one go)
limit_maximum = 1000

max_tries = 3

WEBHOST = "https://connect.garmin.com"
REDIRECT = "https://connect.garmin.com/post-auth/login"
BASE_URL = "http://connect.garmin.com/en-US/signin"
GAUTH = "http://connect.garmin.com/gauth/hostname"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css"

data = {'service': REDIRECT,
    'webhost': WEBHOST,
    'source': BASE_URL,
    'redirectAfterAccountLoginUrl': REDIRECT,
    'redirectAfterAccountCreationUrl': REDIRECT,
    'gauthHost': SSO,
    'locale': 'en_US',
    'id': 'gauth-widget',
    'cssUrl': CSS,
    'clientId': 'GarminConnect',
    'rememberMeShown': 'true',
    'rememberMeChecked': 'false',
    'createAccountShown': 'true',
    'openCreateAccount': 'false',
    'usernameShown': 'false',
    'displayNameShown': 'false',
    'consumeServiceTicket': 'false',
    'initialFocus': 'true',
    'embedWidget': 'false',
    'generateExtraServiceTicket': 'false'}

print urllib.urlencode(data)

# URLs for various services.
url_gc_login = 'https://sso.garmin.com/sso/login?' + urllib.urlencode(data)
# URLs for various services.
url_gc_post_auth = 'https://connect.garmin.com/modern/activities?'
url = 'https://connect.garmin.com/modern/proxy/activitylist-service/activities/comments/group/GROUPID?&start=0&limit=500'


## Initially, we need to get a valid session cookie, so we pull the login page.
print 'Request login page'
http_req(url_gc_login)
print 'Finish login page'

# Now we'll actually login.
post_data = {'username': username, 'password': password, 'embed': 'true', 'lt': 'e1s1', '_eventId': 'submit', 'displayNameRequired': 'false'}  # Fields that are passed in a typical Garmin login.
print 'Post login data'
login_response = http_req(url_gc_login, post_data)
print 'Finish login post'

# extract the ticket from the login response
pattern = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
match = pattern.match(login_response)
if not match:
	raise Exception(
		'Did not get a ticket in the login response. Cannot log in. Did you enter the correct username and password?')
login_ticket = match.group(1)
print 'login ticket=' + login_ticket

print 'Request authentication'
# print url_gc_post_auth + 'ticket=' + login_ticket
http_req(url_gc_post_auth + 'ticket=' + login_ticket)
print 'Finished authentication'

# We should be logged in now.
if not isdir(activities_directory):
    mkdir(activities_directory)
result = http_req(url)
json_results = json.loads(result)

#setup connection to the dtw server
conn = mysql.connect(host='IPADDRESS', user='USER', passwd='PASSWORD', db='DATABASE')
conn.autocommit(True)
cursor = conn.cursor()

# gets newest timestamp from the database
cursor.execute('select * from TABLE ORDER BY ID DESC limit 1')
latestrecord = cursor.fetchone()

f = open(str(activities_directory) + '/snapshot.csv', 'w')


# Read the data into a panda and then out to a csv
df = pd.read_sql('select * from TABLE ORDER BY ID DESC', conn)
df.to_csv(f, header=True)

print 'Data backup completed'

# The newest date and activityID in the database
print latestrecord[6]
print latestrecord[1]

# Remember to set the date
for item in json_results['activityList']:
    # If activity ID is greater than the latest
    if item["activityId"] > latestrecord[1]:

        #We need to sanitize all data being entered into the database
        activityname = item["activityName"]
        if activityname is not None:
            activityname = mysql.escape_string(
                unicodedata.normalize('NFKD', item["activityName"]).encode('ascii', 'ignore'))

        desc = item["description"]
        if desc is not None:
            desc = mysql.escape_string(unicodedata.normalize('NFKD', item["description"]).encode('ascii', 'ignore'))

        displayname = item["ownerDisplayName"]

        fullname = item["ownerFullName"]
        if fullname is not None:
            fullname = bleach.clean(str(item["ownerFullName"]))

        #Build up query and execute
        cursor.execute(
            "INSERT INTO TABLE(VAL, VAL, VAL, VAL, VAL,"
            " VAL, VAL, VAL, VAL, VAL, VAL, VAL) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (int(item["activityId"]), int(item["activityType"]["typeId"]),
             str(item["activityType"]["typeKey"]), str(activityname), str(desc),
             item["startTimeLocal"], item["startTimeLocal"], float(item["distance"]),
             float(item["duration"]), int(item["ownerId"]), displayname, fullname))


#Clean up
cursor.close()
conn.commit()
conn.close()

print 'Done!'
