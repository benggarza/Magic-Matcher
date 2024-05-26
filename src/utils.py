from bs4 import BeautifulSoup
import pandas
import requests
from unidecode import unidecode
import re

# evaluates if the given color identity string is a valid string for scryfall
def valid_ci(ci : str):
    valid = True
    # first assume they wrote it in wubrg style, make sure each character in wubrg
    for c in ci:
        if c not in 'wubrg':
            valid = False
    # then take account for color pair/wedge/shards
    if ci in ['rakdos','golgari','selesnya','boros','dimir','azorius','orzhov', 'izzet', 'simic','gruul']:
        valid = True
    if ci in ['jund', 'naya', 'bant', 'mardu', 'esper', 'jeskai', 'grixis', 'sultai', 'abzan', 'temur']:
        valid = True
    # then take account for colorless
    if ci == 'c':
        valid = True
    return valid

# given a series of names, format them into keys for edhrec.com
def format_keys(names : pandas.Series) -> list:
    _keys = names.apply(lambda name: unidecode(re.sub(' \/\/.*', '', name)))
    _keys = _keys.apply(lambda name: re.sub('[^a-zA-Z0-9\- ]', '', name))
    _keys = _keys.apply(lambda name: re.sub('[ ]{2,}', ' ', name))
    keys = _keys.apply(lambda _name: re.sub(' ', '-', _name).lower()).to_list()
    return keys

# score function for cards
# low sample sizes get reduced impact scores due to high variance
def get_score(num : int, potential : int, synergy : float, pdh : bool = False) -> float:
    #return 1 + (1-math.exp(-(num/potential)))/(1-math.exp(-1))
    #return 2-((num/potential)-1)**2
    if potential < 5:
        return 1 + ((num-0.5)/potential)**2 + max(0,synergy-0.5)
    return 1 + (num/potential)**2 + max(0,synergy)

# given a score and a list of top scores, return the proper index or -1
def get_index_rank(candidate_score : float, top_scores : list):
    for i in range(len(top_scores)):
        if candidate_score > top_scores[i]:
            return i
    return -1

# insert element i into list l
def insert(elem, i : int, l : list):
    temp = l[i]
    l[i] = elem
    for ind in range(i+1, len(l)):
        shift_elem = temp
        temp = l[ind]
        l[ind] = shift_elem

def get_cardlist(key : str, pauper : bool = False):
    if pauper:
        # Scrape pdhrec for cardlist, and put it into a dict with cols : name, num_decks, potential_decks
        pdhrec_page = requests.get(f'https://www.pdhrec.com/commander/{key}/')
        soup = BeautifulSoup(pdhrec_page.text, 'html.parser')
        potential_decks = 0

        # get the total number of decks, the first one found should be the one we want
        try:
            info = soup.find('div', attrs={"class":"info"})
            potential_decks = int(re.search(r'\d+', info.string).group())
        except:
            return None

        cardlist = []
        # warning! this search also finds the commander element, should be the first
        hyperlinks = soup.find_all('a', attrs={"class":"gallery-item"})
        for hyperlink in hyperlinks[1:]:
            name = ''
            card = hyperlink.contents[1]
            # double faced cards have a wrapper to show both sides at same time
            if card.name == 'div':
                card = card.contents[1].contents[3]
                print(f'dfc {card["alt"]}')
            name = card['alt']

            num_decks = potential_decks
            
            try:
                num_decks = int(hyperlink['popularity'])
            except:
                #print(f'Found a weird page for {key}, not calculating usage rate (setting num_decks for {name} to {num_decks})')
                pass

            synergy = 0
            try:
                synergy = float(hyperlink['synergy'])
            except:
                pass

            cardlist.append({'name':name, 'num_decks':num_decks, 'potential_decks':potential_decks, 'synergy':synergy})
        return cardlist
    else:
        # Grab the json from edhrec
        edhrec_json = requests.get(f'https://json.edhrec.com/pages/commanders/{key}.json').json()

        cardlist = []
        try:
            cardlist = edhrec_json['cardlist']
        except:
            print('get_cardlist: edhrec json is empty')
            return None
        return cardlist
