


import requests
import requests.auth
import json

import hashlib
import time

from flask import Flask, redirect, abort, request

import configparser

config = configparser.ConfigParser()
config.read('config.ini')
settings = config['settings']

configfile_locked = False

auth_uri="https://www.twitchalerts.com/api/v1.0/authorize"
token_uri="https://www.twitchalerts.com/api/v1.0/token"
donation_uri="https://www.twitchalerts.com/api/v1.0/donations"
scope='donations.create'
redirect_uri="http://localhost:8080/twitchalerts"
token_expiry = 3600
headers={'content-type': 'application/json'}


app = Flask(__name__)

@app.route('/')
def homepage():
	login_status = settings.get('refresh_token',None)
	registered_status = settings.get('client_id',None)
	if registered_status is None:
		return redirect('http://localhost:8080/initial_setup')
	elif login_status is None:
		return redirect('http://localhost:8080/authorize')
	else:
		return redirect('http://localhost:8080/control')

@app.route('/initial_setup', methods=["GET","POST"])
def initial_setup():
	if request.method == "POST":
		settings['client_id'] = request.form['client_id']
		settings['client_secret'] = request.form['client_secret']
		write_config()
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
			settings['donations_page'] = request.form['donations_page']
			settings['refresh'] = request.form['refresh']
			write_config()
			page += "<p>Settings updated.</p>"
		elif request.form['action'] == 'test_extralife':
			donations = get_extralife_donations()
			for d in donations:
				post_donation(**d)
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

def write_config():
	global configfile_locked
	while configfile_locked:
		pass
	configfile_locked = True
	with open('config.ini','w') as configfile:
		config.write(configfile)
	configfile_locked = False


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
	donations_page = settings.get('donations_page','')
	refresh = int(settings.get('refresh'))
	
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
	params = {"client_id": settings['client_id'],
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
	client_auth = requests.auth.HTTPBasicAuth(settings['client_id'], settings['client_secret'])
	post_data = {	"grant_type": "authorization_code",
					"code": code,
					"redirect_uri": redirect_uri}
	response = requests.post(token_uri,auth=client_auth,data=post_data)
	token_json = response.json()
	settings['access_token'] = token_json['access_token']
	settings['refresh_token'] = token_json['refresh_token']
	settings['token_created_at'] = str(time.time())
	write_config()
	return token_json["access_token"]

def renew_token():
	client_auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
	post_data = {	"grant_type": "refresh_token",
					"client_id": client_id,
					"client_secret": client_secret,
					"redirect_uri": redirect_uri,
					"refresh_token": settings['refresh_token']}
	response = requests.post(token_uri,auth=client_auth,data=post_data)
	token_json = response.json()
	settings['access_token'] = token_json['access_token']
	settings['refresh_token'] = token_json['refresh_token']
	settings['token_created_at'] = time.time()
	write_config()
	return token_json['access_token']

def get_token():
	if time.time() > float(settings['token_created_at']) + token_expiry:
		return renew_token()
	else:
		return settings['access_token']

def post_donation(**kwargs):
	data = {	'access_token': get_token(),
				'name': kwargs['name'],
				'identifier': kwargs['identifier'],
				'amount': kwargs['amount'],
				'currency': kwargs.get('currency','USD'),
				'message': kwargs.get('message',None)}
	r = requests.post("https://www.twitchalerts.com/api/v1.0/donations", data=data)
	return r.json()

def get_username(token):
	url = 'https://www.twitchalerts.com/api/v1.0/user'
	params={'access_token': token}
	headers={'content-type': 'application/json'}
	r = requests.get(url, headers=headers,params=params)
	return r.json()

def get_extralife_donations():
	if settings.get('donations_page',None) is not None and settings['donations_page'] != '':
		params = {'format':'json'}
		r = requests.get(settings['donations_page'], headers=headers, params=params)
		results = r.json()
		print('Results:')
		print(results)
		donations = []
		for donation in results:
			identifier = ("%s %s" % (donation['createdOn'],donation['donorName'])).encode()
			donations.append({	'name':donation['donorName'].replace(' ','_'),
								'message':donation['message'],
								'identifier':hashlib.md5(identifier).hexdigest(),
								'amount':donation['donationAmount'],
								'created_at':donation['createdOn']})
		print(donations)
		return donations
	else:
		return None




if __name__ == '__main__':
	app.run(debug=True, port=8080)