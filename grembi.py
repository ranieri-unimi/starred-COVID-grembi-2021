import googlemaps
import time
import numpy as np
import math
import selenium
import re
import pickle

from bs4 import BeautifulSoup

import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

GRT = 0.85 # distorsione terrestre a milano
ROF = 1.25 # radar overflow
AK = pickle.load(open("C:/Users/Martin/OneDrive/onlyfans.pk", "rb"))

_gmaps = googlemaps.Client(key=AK)
_driver = None

base_uri = 'https://www.google.com/maps/'
res_uri = 'place/?q=place_id:'
cute_types = ['meal_delivery', 'meal_takeaway', 'restaurant', 'bar', 'cafe', ]
red_types = ['delivery_takeaway', 'restaurant', 'bar_cafe', ]
cute_attr = ['name', 'place_id', 'price_level', 'rating', 'user_ratings_total', ]
ren_attr = ['place_name', 'place_id', 'price_level', 'avg_stars', 'place_popularity', ]

def breath(deep=2.0):
    time.sleep(deep)

def to_radio(meters):
    return (0.000009)*2*meters/math.sqrt(3)

def to_int(s, default=0):
    tmp = re.sub("[^0-9]", "", s)
    return int(tmp) if tmp else default

def get_radars(meters, south_west, north_east, **kwargs):
    radar_spot = []
    radio = to_radio(meters)
    s2n = south_west[0]
    odd = False
    while s2n < north_east[0]:
        w2e = GRT*3*radio*odd + south_west[1]
        while w2e < north_east[1]:
            radar_spot.append((s2n,w2e))
            w2e += GRT*6*radio
        s2n += radio
        odd = not odd
    return radar_spot

def get_places(margs):
    global _gmaps
    all_places = []
    response = _gmaps.places_nearby(**margs)
    all_places += response['results']
    while ('next_page_token' in response and response['next_page_token']):
        breath()
        try:
            response = _gmaps.places_nearby(page_token = response['next_page_token'])
        except:
            print('unhandled api burned')
        else:
            all_places += response['results']
    return all_places

def clean_place(obj):
    x = {k:obj.get(k, None) for k in cute_attr}
    for t in cute_types:
        x[t] = t in obj['types']
        
    # LEGACY EDIT
    x['delivery_takeaway'] = x['meal_delivery'] or x['meal_takeaway']
    x['bar_cafe'] = x['bar'] or x['cafe']
    
    return x

def get_reviews(pid, max_reviews=1000):
    global _driver
    soup = None
    try:
        _driver.get(base_uri+res_uri+pid)

        menu_bt = WebDriverWait(_driver, 7).until(EC.element_to_be_clickable((By.XPATH, '//button[@data-value=\'Sort\']')))
        menu_bt.click()

        recent_rating_bt = WebDriverWait(_driver, 7).until(EC.element_to_be_clickable((By.XPATH, '//li[@data-index=\'1\']')))
        recent_rating_bt.click()

        last_len = 0
        sentinel = 0
        for i in range(max_reviews//10):
            breath(1)
            scrollable_div = _driver.find_element_by_css_selector('div.section-layout.section-scrollbox.scrollable-y.scrollable-show')
            _driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)

            soup = BeautifulSoup(_driver.page_source, 'html.parser').find_all('div', class_='section-review-content')

            if len(soup) == last_len:
                sentinel += 1
            else:
                sentinel = 0
            if sentinel > 2:
                break
            last_len = len(soup)
    except:
        print('raised exception ignored on', pid)
    return soup

def clean_review(r):
    x = {
        'id': r.find('button',class_='section-review-action-menu')['data-review-id'],
        'user_name': r.find('div', class_='section-review-title').find('span').text,
        'stars': to_int(r.find('span', class_='section-review-stars')['aria-label']),
        'value_date': r.find('span', class_='section-review-publish-date').text.split()[0],
        'unit_date': r.find('span', class_='section-review-publish-date').text.split()[1],
    }
    
    x['days_ago'] = get_time(**x)
    
    try:
        x['text'] = ' '.join(r.find('span', class_='section-review-text').text.split())
    except:
        x['text'] = ''
    
    try:
        sub = r.find('div', class_='section-review-subtitle')
        spn = sub.findAll('span')
    except:
        x['user_popularity'] = 1
        x['is_player'] = 0
    else:
        if len(spn) > 1:
            x['user_popularity'] = to_int(spn[1].text, 1)
            x['is_player'] = 1 if len(sub.find_all(attrs={"style" : "display:none"})) else 0
    return x

def get_time(value_date, unit_date, **kwargs):
    word2days = {
        'second': 1,
        'minute': 1,
        'hour': 1,
        'day': 1,
        'week': 7,
        'month': 30,
        'year': 365,
    }
    if unit_date in word2days:
        return word2days[unit_date]
    else:
        return to_int(value_date)*word2days[unit_date[:-1]]
    
def init_driver():
    global _driver
    _driver = webdriver.Chrome()
    _driver.get(base_uri)
    WebDriverWait(_driver, 7).until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//iframe")))
    agree = WebDriverWait(_driver, 7).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="introAgreeButton"]/span/span'))) 
    agree.click()
    _driver.switch_to.default_content()
    
def kill_driver():
    global _driver
    _driver.quit()
    
def sample_viewport(meters, viewport):
    places_db = []
    for t in cute_types:
        for r in get_radars(meters, **viewport):
            margs = {
                'location':r,
                'radius':meters*ROF,  
                'type':t,
            }
            places_db += get_places(margs)
    return places_db

def scrape_reviews(pid_list, min_reviews):
    reviews_db = dict()
    init_driver()
    for pid in pid_list:
        rw_soup = get_reviews(pid, min_reviews)
        reviews_db[pid] = []
        if rw_soup:
            for r in rw_soup:
                reviews_db[pid].append(str(r))
    kill_driver()
    return reviews_db

def purify_data(places_db):
    data = [clean_place(p) for p in places_db]
    data = [i for i in data if i['user_ratings_total'] or i['rating']]
    tmp = dict()
    
    for i in data:
        pid = i['place_id']
        if pid not in tmp:
            tmp[pid] = []
        tmp[pid].append(i)

    for k,v in tmp.items():
        x = dict()
        for i in v:
            x = {**x, **i}
        tmp[k] = x

    return list(tmp.values())

def enrich_data(data, reviews_db):
    for i in data:
        i['reviews'] = []
        for r in reviews_db[i['place_id']]:
             i['reviews'].append(clean_review(BeautifulSoup(r)))
    return data