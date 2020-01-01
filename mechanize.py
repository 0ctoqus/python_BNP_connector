#!/usr/bin/env python
# coding: utf-8

from selenium import webdriver
from selenium.webdriver.common.keys import Keys

import cv2
import numpy as np

import glob
import os

import random
import time

import pandas as pd

from sqlalchemy import create_engine

if 'CLIENT_NBR' in os.environ and 'CLIENT_PASS' in os.environ and 'DB_PASS' in os.environ:
	CLIENT_NBR = os.environ['CLIENT_NBR']
	CLIENT_PASS = os.environ['CLIENT_PASS']
	DB_PASS = os.environ['DB_PASS']
else:
	print("You need to set CLIENT_NBR, CLIENT_PASS and DB_PASS in the environement")
	exit(0)

DOMAIN = 'mabanque.bnpparibas'
DOWNLOAD_DIR = "."
HEADLESS = True
OUPUT_NAME = "extracted"

#DB infos
hostname = '192.168.0.100'
port = '3306'
username = 'BANK'
password = DB_PASS
database = 'bank'
table = 'bnp_octave'

#Account context
initial_amount = 0

#Execustion params
keyboard_path = 'keyboard.png'

def open_browser():
	def enable_download_in_headless_chrome(driver, download_dir):
	    # add missing support for chrome "send_command"  to selenium webdriver
	    driver.command_executor._commands["send_command"] = ("POST",'/session/$sessionId/chromium/send_command')
	    params = {'cmd': 'Page.setDownloadBehavior', 'params': {'behavior': 'allow', 'downloadPath': download_dir}}
	    command_result = driver.execute("send_command", params)

	options = webdriver.ChromeOptions()
	#options.binary_location("./lib/python3.6/site-packages/chromedriver_binary/chromedriver")
	
	if HEADLESS:
		options.add_argument('--no-sandbox')
		options.add_argument('--window-size=3000,3000')
		options.add_argument('--headless')
		options.add_argument('--disable-gpu')
		
		options.add_argument('--shm-size=1024m')
		options.add_argument('-cap-add=SYS_ADMIN')

	options.add_experimental_option("prefs", { \
    'download.default_directory': DOWNLOAD_DIR,
     'download.prompt_for_download': False,
     'download.directory_upgrade': True,
  	})

	driver = webdriver.Chrome(options= options)

	driver.get("https://%s/fr/connexion/" % DOMAIN)
	if HEADLESS:
		enable_download_in_headless_chrome(driver, DOWNLOAD_DIR)
	driver.implicitly_wait(10)
	return driver

# Download the keyboard image
def get_keybord(driver):
	# Get element
	secret_nbr_keyboard = driver.find_element_by_id("secret-nbr-keyboard")

	# Get url
	keyboard_url = secret_nbr_keyboard.value_of_css_property('background-image').split("\"")[1]
	current_tab = driver.current_window_handle

	# Get image
	window_before = driver.window_handles[0]
	driver.execute_script('window.open();')
	new_tab = [tab for tab in driver.window_handles if tab != current_tab][0]
	driver.switch_to.window(new_tab)
	driver.get(keyboard_url)
	driver.save_screenshot(keyboard_path)
	driver.close()
	driver.switch_to.window(window_before)

# Open our existing keyboard digits to compare to
def open_digits():
	digits = {}
	for filename in glob.glob(os.path.join(os.getcwd() + "/digits", '*.png')):
		nb = int(filename.split("/")[-1].split(".")[0])
		digits[nb] = cv2.imread(filename)

	return digits

# Crop an image depending on color and bin
def crop_keys(img, min, max, bin):
	## (1) Convert to gray, and threshold
	gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	th, threshed = cv2.threshold(gray, min, max, bin)

	## (2) Morph-op to remove noise
	kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11,11))
	morphed = cv2.morphologyEx(threshed, cv2.MORPH_CLOSE, kernel)

	## (3) Find the max-area contour
	cnts = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
	cnt = sorted(cnts, key=cv2.contourArea)[-1]

	## (4) Crop and save it
	x,y,w,h = cv2.boundingRect(cnt)
	dst = img[y:y+h, x:x+w]

	return dst

# Split our keyboard image into digits
def generate_digits(img):
	height, width = img.shape[:2]
	height /= 2
	width /= 5
	accu = 0
	margin = 10

	for row in range(0, 2):
		for column in range(0, 5):
			start_row, start_col = int(height * row), int(width * column) 
			end_row, end_col = int(height * (row + 1)), int(width * (column + 1))
			cropped = img[start_row + margin:end_row - margin, start_col + margin:end_col - margin]
			cv2.imwrite("./digits/unsorted_" + str(accu) + ".png", crop_keys(cropped, 235, 255, cv2.THRESH_BINARY_INV))
			accu += 1

# Iterate over our digits image and compare them to our existing sample
def find_keys(img, digits):
	height, width = img.shape[:2]
	height /= 2
	width /= 5
	accu = 0
	margin = 10
	threshold = 0.95

	results = {}
	for row in range(0, 2):
		for column in range(0, 5):
			# We get only the black number in the image
			start_row, start_col = int(height * row), int(width * column) 
			end_row, end_col = int(height * (row + 1)), int(width * (column + 1))
			cropped = img[start_row + margin:end_row - margin, start_col + margin:end_col - margin]
			current_digit = cropped#crop_keys(cropped, 235, 255, cv2.THRESH_BINARY_INV)
			c_height, c_width = current_digit.shape[:2]

			#cv2.imwrite("./tmp/" + str(row) + "_" + str(column) + ".png", current_digit)

			#We iterate over each loaded digit
			for digit in digits:
				template = digits[digit]
				#t_height, t_width = template.shape[:2]

				# Apply template Matching
				res = cv2.matchTemplate(template, current_digit, cv2.TM_CCOEFF_NORMED)

				loc = np.where(res >= threshold)
				if (loc[::-1][0].size):
					#cv2.imwrite("./tmp/" + str(digit) + ".png", current_digit)
					results[digit] = accu
			
			accu += 1

	if len(results) != 10:
		print ("Error, we were not able to find all 10 digits, only found", len(results))
		exit(0)
	return results

def connect(driver):
	print ("Closing coockies footer")
	driver.find_element_by_xpath("/html/body/section/button").click()

	def enter_client_nbr(driver, nbr):
		client_nbr = driver.find_element_by_id("client-nbr")
		client_nbr.send_keys(nbr)

	enter_client_nbr(driver, CLIENT_NBR)
	driver.implicitly_wait(3)
	get_keybord(driver)

	img = cv2.imread(keyboard_path)
	#os.remove('keyboard.png')

	img = crop_keys(img, 100, 255, cv2.THRESH_BINARY)

	digits = open_digits()

	if len(digits.keys()) != 10:
		print ("We generate the digits, please you need to rename them")
		generate_digits(img)
		driver.quit()

	key_map = find_keys(img, digits)
	secret_nbr_keyboard = driver.find_element_by_id("secret-nbr-keyboard").find_elements_by_tag_name("a")

	for digit in CLIENT_PASS:
		key = key_map[int(digit)]
		secret_nbr_keyboard[key].click()
		time.sleep(random.uniform(0.3, 0.8))

	driver.find_element_by_id("submitIdent").click()

def download(driver):
	# Opening fav account and clicking on download transaction history
	print ("Selecting account")
	time.sleep(3)
	driver.find_element_by_class_name("folder-btn").click()
	time.sleep(random.uniform(0.3, 0.8))
	driver.find_element_by_xpath("/html/body/div[1]/div/div[3]/div[1]/div[1]/div[1]/div[4]/div/div/div[2]/div/section[3]/div[1]/section/div[1]/ul[1]/li/div[3]/div/button[6]").click()
	time.sleep(random.uniform(1, 3))

	# Select operation to download
	print ("Selecting download type")
	driver.find_element_by_xpath("/html/body/div[1]/div/div[3]/div/div[1]/div/div[4]/div/div/div[2]/div/section/form/fieldset[1]/div/label[5]").click()
	driver.find_element_by_id("next-button").click()

	# Click Download
	print ("Downloading")
	driver.execute_script("window.scrollTo(0, 0)") 
	driver.find_element_by_xpath("/html/body/div[1]/div/div[3]/div/div[1]/div/div[4]/div/div/div[2]/div/section/div/table/tbody/tr/td[4]/a").click()
	#driver.implicitly_wait(10)
	time.sleep(5)

def change_pass(driver):
	driver.get("https://%s/fr/espace-prive/mes-outils/profil/code-secret" % DOMAIN)
	time.sleep(10)
	get_keybord(driver)

	img = cv2.imread(keyboard_path)
	#os.remove('keyboard.png')
	img = crop_keys(img, 100, 255, cv2.THRESH_BINARY)

	digits = open_digits()
	if len(digits.keys()) == 0:
		print ("We generate the digits, please you need to rename them")
		generate_digits(img, digits)
		driver.quit()
		exit(0)

	key_map = find_keys(img, digits)
	secret_nbr_keyboard = driver.find_element_by_id("secret-nbr-keyboard").find_elements_by_tag_name("a")

	# we enter the current password
	for digit in CLIENT_PASS:
		key = key_map[int(digit)]
		secret_nbr_keyboard[key].click()
		time.sleep(random.uniform(0.3, 0.8))
	#driver.find_element_by_id("submitIdent").click()

def handle_result():
	def open_result():
		def get_path():
			for file in os.listdir(DOWNLOAD_DIR):
				if file.endswith(".csv"):
					return os.path.join(DOWNLOAD_DIR, file)
			return None

		csv_path = get_path()
		if csv_path == None:
			print("Csv not found")
			exit(0)

		# We open the file
		columns = ["DateOperation", "LibelleCourt", "TypeOperation", "LibelleOperation", "MontantOperation"]
		types = {"DateOperation" : "str", "LibelleCourt" : "str", "TypeOperation" : "str", "LibelleOperation" : "str", "MontantOperation" : "str"}
		dates_columns = ["DateOperation"]

		df = pd.read_csv(csv_path,
			index_col= None,
			skiprows= 1, 
			names= columns, 
			dtype= types,
			parse_dates = dates_columns,
			sep= ';')

		# We convert the values
		df["MontantOperation"] = [x.replace(',', '.').replace(' ', '') for x in df["MontantOperation"]]
		df["MontantOperation"] = df["MontantOperation"].astype(float)

		# We calculate the initial ammount on the account
		infos = list(pd.read_csv(csv_path, encoding="latin-1", nrows=1, sep= ';'))
		df["TypeCompte"]	= infos[0]
		df["LibelleCompte"]	= infos[1]
		df["NumeroCompte"]	= infos[2]
		df["DateExtract"]	= pd.to_datetime(infos[3])
		df["Unnamed"] 		= int(infos[4].split(" ")[1])

		# We delete the file
		os.remove(csv_path)

		# Initial amout is equal to obeserved MontantCourant - df["MontantOperation"].sum()
		global initial_amount
		initial_amount = float(infos[5].replace(',', '.')) - df["MontantOperation"].sum()

		return df

	def open_existing():
		try:
			return pd.read_parquet(OUPUT_NAME + '.gzip')
		except:
			return None

	new_df = open_result()

	old_df = open_existing()
	#We dont have a file so we just create it
	if old_df is None:
		new_df.to_parquet(OUPUT_NAME + '.gzip', compression='gzip')
		return new_df

	#We merge both dataframe and creat a new column depending on if the row in new or not
	df_all = new_df.merge(old_df, on= list(old_df.columns), how= 'left', indicator= True)

	#We get only our new operations
	df_all_filtered = df_all[df_all['_merge'] == 'left_only'].drop(columns= ["_merge"])
	if df_all_filtered.empty:
		print("No new operations")
		exit(0)

	#We save all the merged operations
	df_all = df_all.drop(columns= ["_merge"])
	df_all.to_parquet(OUPUT_NAME + '.gzip', compression='gzip')
	return df_all_filtered

def calcule_fields(df):
	# We calculate our running total
	size = len(df) - 1

	# We calculate our running total
	df.loc[size, "MontantCourant"] = df.loc[size,  "MontantOperation"] + initial_amount
	for i in range(size - 1, -1, -1):
		df.loc[i, "MontantCourant"] = df.loc[i, "MontantOperation"] + df.loc[i + 1, "MontantCourant"]

	# We modify the date so we dont lose our order information
	last_date = None
	current_ordre = 1
	df["NumeroOperation"] = 0
	for i in range(size, -1, -1):
		current_date = df.loc[i, "DateOperation"]
		if current_date != last_date:
			last_date = current_date
			current_ordre = 1
		else:
			current_ordre += 1
		df.loc[i, "NumeroOperation"] = current_ordre

	return df

def upload_result(df):
	print ("We have", len(df), "new records")
	mydb = create_engine('mysql://' + username + ':' + password + "@" + hostname + ":" + port + "/" + database, echo=False)
	print ("Adding results")
	df.to_sql(name= table, con= mydb, if_exists= 'replace', index= False)
	print ("Done")

driver = open_browser()
connect(driver)
download(driver)
#change_pass(driver)
driver.quit()
df = handle_result()
df = calcule_fields(df)
upload_result(df)


