


import requests
import requests.auth
import json

import hashlib
import time

from flask import Flask, redirect, abort, request

import shelve

import threading

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


configfile_locked = False

auth_uri="https://www.twitchalerts.com/api/v1.0/authorize"
token_uri="https://www.twitchalerts.com/api/v1.0/token"
donation_uri="https://www.twitchalerts.com/api/v1.0/donations"
scope='donations.create'
redirect_uri="http://localhost:8080/twitchalerts"
token_expiry = 3600
default_refresh = 60
headers={'content-type': 'application/json'}



app = Flask(__name__)

@app.route('/')
def homepage():
	login_status = read_setting('refresh_token')
	registered_status = read_setting('client_id')
	if registered_status is None:
		return redirect('http://localhost:8080/initial_setup')
	elif login_status is None:
		return redirect('http://localhost:8080/authorize')
	else:
		return redirect('http://localhost:8080/control')

@app.route('/initial_setup', methods=["GET","POST"])
def initial_setup():
	if request.method == "POST":
		write_setting('client_id',request.form['client_id'])
		write_setting('client_secret',request.form['client_secret'])
		return redirect('http://localhost:8080/authorize')
	else:
		page = "<form action='http://localhost:8080/initial_setup' method='post'>\n"
		page += "<p>Register a new application at <a herf='http://twitchalerts.com/oauth/apps/register' target='_blank'>http://twitchalerts.com/oauth/apps/register</a></p>\n"
		page += "<p>Application name doesn't matter. Redirect URI should be set to 'http://localhost:8080/twitchalerts'</p>\n"
		page += "<p>Enter the Client ID and Client Secret given below.</p>\n"
		page += "Client ID<input type='text' name='client_id'/><br/>\n"
		page += "Client Secret<input type='text' name='client_secret'/><br/>\n"
		page += "<button>Submit</button></form>"
		return page


@app.route('/authorize')
def authorize():
	text = "<form action='" + auth_uri+ "' method='get'>%s<button>Authorize With TwitchAlerts</button></form>"
	return text % make_hidden_inputs()

@app.route('/control', methods=['GET','POST'])
def control():
	page = ""
	if request.method == 'POST':
		if request.form['action'] == 'test_donation':
			result = post_donation(name="Test_Donator",identifier="test@test.com",amount=5,message="Test message")
			page += "<p>Test donation posted.</p>"
			page += str(result)
		elif request.form['action'] == 'config':
			write_setting('donations_page',request.form['donations_page'])
			write_setting('refresh',int(request.form['refresh']))
			page += "<p>Settings updated.</p>"
		elif request.form['action'] == 'test_extralife':
			donations = get_extralife_donations()
			for d in donations:
				post_donation(override=True,**d)
	page += config_form()
	page += test_donation_button()
	page += test_extralife_button()

	return page

@app.route('/twitchalerts')
def twitchalerts():
	error = request.args.get('error','')
	if error:
		return "Error: " + error
	code = request.args.get('code')
	init_token(code)
	return redirect("http://localhost:8080/control")


def test_donation_button():
	form = ""
	form += "<form action='http://localhost:8080/control' method='post'>\n"
	form += "<input type='hidden' name='action' value='test_donation'/>\n"
	form += "<button>Post Test Donation</button>\n"
	form += "</form>"
	return form

def test_extralife_button():
	form = ""
	form += "<form action='http://localhost:8080/control' method='post'>\n"
	form += "<input type='hidden' name='action' value='test_extralife'/>\n"
	form += "<button>Test From Extra Life</button>\n"
	form += "</form>"
	return form

def config_form():
	donations_page = read_setting('donations_page','')
	refresh = read_setting('refresh',default_refresh)
	
	form = ""
	form += "<form action='http://localhost:8080/control' method='post'>\n"
	form += "<input type='hidden' name='action' value='config'/>\n"
	form += "Extra Life Donations Page:<input type='text' name='donations_page'/ value='%s'><br/>\n" % donations_page
	form += "Refresh(secs):<input type='text' name='refresh' value='%s'/><br/>\n" % refresh
	form += "<button>Submit</button>"
	form += "</form>"
	return form


def make_hidden_inputs():
	# Generate a random string for the state parameter
	# Save it for use later to prevent xsrf attacks
	#from uuid import uuid4
	#state = str(uuid4())
	#save_created_state(state)
	params = {"client_id": read_setting('client_id'),
				"response_type": "code",
				#"state": state,
				"redirect_uri": redirect_uri,
				"duration": "temporary",
				"scope": scope}
	inputs = ""
	for key in params.keys():
		inputs += "<input type='hidden' name='%s' value='%s' />" % (key,params[key])
	return inputs



def init_token(code):
	client_auth = requests.auth.HTTPBasicAuth(read_setting('client_id'), read_setting('client_secret'))
	post_data = {	"grant_type": "authorization_code",
					"code": code,
					"redirect_uri": redirect_uri}
	response = requests.post(token_uri,auth=client_auth,data=post_data)
	token_json = response.json()
	write_setting('access_token',token_json['access_token'])
	write_setting('refresh_token',token_json['refresh_token'])
	write_setting('token_created_at',time.time())
	return token_json["access_token"]

def renew_token():
	client_auth = requests.auth.HTTPBasicAuth(read_setting('client_id'), read_setting('client_secret'))
	post_data = {	"grant_type": "refresh_token",
					"client_id": client_id,
					"client_secret": client_secret,
					"redirect_uri": redirect_uri,
					"refresh_token": settings['refresh_token']}
	response = requests.post(token_uri,auth=client_auth,data=post_data)
	token_json = response.json()
	write_setting('access_token',token_json['access_token'])
	write_setting('refresh_token',token_json['refresh_token'])
	write_setting('token_created_at',time.time())
	return token_json['access_token']

def get_token():
	if time.time() > read_setting('token_created_at') + token_expiry:
		return renew_token()
	else:
		return read_setting('access_token')

def post_donation(override=False,**kwargs):
	posted = read_setting('posted_donations',[])
	if kwargs['identifier'] not in posted or override:
		data = {	'access_token': get_token(),
					'name': kwargs['name'],
					'identifier': kwargs['identifier'],
					'amount': kwargs['amount'],
					'currency': kwargs.get('currency','USD'),
					'message': kwargs.get('message',None)}
		r = requests.post("https://www.twitchalerts.com/api/v1.0/donations", data=data)
		posted.append(kwargs['identifier'])
		write_setting('posted_donations',posted)
		print_donation(kwargs)

	

def get_username(token):
	url = 'https://www.twitchalerts.com/api/v1.0/user'
	params={'access_token': token}
	headers={'content-type': 'application/json'}
	r = requests.get(url, headers=headers,params=params)
	return r.json()

def verify_setup():
	required = []
	required.append(read_setting('client_id'))
	required.append(read_setting('client_secret'))
	required.append(read_setting('refresh_token'))
	required.append(read_setting('access_token'))
	required.append(read_setting('donations_page'))
	verified = True
	for r in required:
		if r is None:
			verified = False
	return verified



def threaded_donation_scan(start_in=0):
	while not verify_setup():
		time.sleep(10)
	time.sleep(start_in)
	donations = get_extralife_donations()
	for d in donations:
		post_donation(**d)
	threaded_donation_scan(start_in=read_setting('refresh',default_refresh))


def get_extralife_donations():
	donations_page = read_setting('donations_page')
	if donations_page is not None and donations_page != '':
		params = {'format':'json'}
		r = requests.get(donations_page, headers=headers, params=params)
		results = r.json()
		donations = []
		for donation in results:
			identifier = ("%s %s" % (donation['createdOn'],donation['donorName'])).encode()
			donations.append({	'name':validate_name(donation['donorName']),
								'message':donation['message'],
								'identifier':hashlib.md5(identifier).hexdigest(),
								'amount':donation['donationAmount'],
								'created_at':donation['createdOn']})
		return donations
	else:
		return None

def print_donation(donation):
	print("[%s] Received donation from: %s Amount: $%s" % (time.strftime('%I:%M %p'), donation['name'], donation['amount']))


def read_setting(setting,default=None):
	global configfile_locked
	while configfile_locked:
		pass
	configfile_locked = True
	settings = shelve.open('config')
	value = settings.get(setting,default)
	settings.close()
	configfile_locked = False
	return value

def write_setting(setting,value):
	global configfile_locked
	while configfile_locked:
		pass
	configfile_locked = True
	settings = shelve.open('config')
	settings[setting] = value
	settings.close()
	configfile_locked = False

def validate_name(name):
	valid_name = ""
	for char in name:
		if char == " ":
			valid_name += "_"
		elif char.isalnum():
			valid_name += char
	return valid_name

if __name__ == '__main__':

	if verify_setup():
		print("\nTo change settings point browser to http://localhost:8080\n")
	else:
		print("\nTo setup point web browser to http://localhost:8080\n")

	refreshThread = threading.Thread(target=threaded_donation_scan)

	refreshThread.start()

	app.run(debug=False, port=8080)