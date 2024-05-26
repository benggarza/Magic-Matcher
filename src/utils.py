from bs4 import BeautifulSoup
import pandas
import requests
from unidecode import unidecode
import re
import time

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

def get_ci_set(ci:str):
    ci_set = {}
    mapping = {'rakdos': {'B','R'}, 'golgari': {'B','G'}, 'selesnya':{'G','W'}, 'boros':{'R','W'}, 'dimir':{'U','B'},
               'azorius': {'W','U'}, 'orzhov':{'W','B'}, 'izzet':{'U','R'}, 'simic':{'U','G'}, 'gruul':{'R','G'},
               'jund':{'B','R','G'}, 'naya':{'R','G','W'}, 'bant':{'G','W','U'}, 'mardu':{'B','R','W'}, 
               'esper':{'B','W','U'}, 'jeskai':{'R','W','U'}, 'grixis':{'B','R','U'}, 'sultai':{'B','U','G'},
               'abzan':{'B','W','G'}, 'temur':{'G','R','U'}}
    if ci in mapping.keys():
        ci_set = mapping[ci]
    elif ci != 'c':
        ci_set = set(ci.upper())
    return ci_set

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

        try:
            redirect = edhrec_json['redirect']
            edhrec_json = requests.get(f'https://json.edhrec.com/pages{redirect}.json').json()
        except:
            pass

        cardlist = []
        try:
            cardlist = edhrec_json['cardlist']
        except:
            print('get_cardlist: edhrec json is empty')
            return None
        return cardlist

def set_partners(commander : pandas.DataFrame):
    partner = 'none'
    # partner with
    if 'Partner with' in commander['keywords']:
        oracle = commander['oracle_text']
        start = oracle.index('Partner with ') + len('Partner with ')
        # 
        end = oracle.index('\n', start)

        # if there is reminder text, find beginning of it 
        # e.g. "Partner with Pako, Arcane Retriever (When this..."
        # end of name is right before parenthesis
        try:
            reminder_text = oracle.index('(', start, end)
            end = reminder_text - 1

        # otherwise, newline indicates end of name "Partner with Amy Pond\nFirst..."
        except:
            pass

        partner = oracle[start:end]
    elif 'Partner' in commander['keywords']:
        partner = 'Partner'
    elif 'Choose a background' in commander['keywords']:  
        partner = 'Background'
    elif 'Friends forever' in commander['keywords']:
        partner = 'Friends forever'
    elif 'Doctor\'s companion' in commander['keywords']:
        partner = 'Doctor\'s companion'
    return partner


def get_scryfall_df(queries : list[str]):
    query_str = ''
    for q in queries:
        query_str += q + '+'
    has_next_page = True
    page=1
    commanders = pandas.DataFrame(columns=['name','color_identity','partner'])
    while has_next_page:
        result_json = requests.get(f'https://api.scryfall.com/cards/search?q={query_str}game%3Apaper&unique=cards&order=edhrec&page={page}&format=json').json()
        has_next_page = result_json['has_more']

        data = pandas.DataFrame(result_json['data'])
        cards = data[['name', 'keywords', 'color_identity', 'oracle_text']]
        #print(cards.head)
        cards['partner'] = cards.apply(set_partners, axis=1)
        cards['color_identity'] = cards['color_identity'].map(lambda ci: set(ci))

        commanders = pandas.concat([commanders, cards[['name', 'color_identity','partner']]])
        #print(commanders.head)
        print(f"{min(page*175, result_json['total_cards'])}/{result_json['total_cards']} ({min(1.0, page*175/result_json['total_cards']):.2%})")
        time.sleep(0.5)
        page += 1
    return commanders

# an inplace augmentation of commanders to add the partner combinations
# these should probably be cross-merges and then modifying columns to get the final result...
def generate_partners(commanders : pandas.DataFrame, pdh : bool = False):
    partner = commanders[commanders['partner']=='Partner'].sort_values(by=['name'])

    partners = []
    for commander in partner.itertuples(index=True):
        for i in range(commander.Index+1, len(partner)):
            commander_partner = partner.iloc[i]
            partners_name = commander.name + ' ' + commander_partner['name']
            partners_color_identity = commander.color_identity | commander_partner['color_identity']
            partners.append([partners_name, partners_color_identity, 'none'])

    background_query = ['t%3Abackground']
    if pdh:
        background_query.append('r%3Auncommon')

    backgrounds = get_scryfall_df(background_query)
    choose_background = commanders[commanders['partner']=='Background'].sort_values(by=['name'])
    for commander in choose_background.itertuples():
        for bg in backgrounds.itertuples():
            cbg_name = commander.name + ' ' + bg.name
            cbg_color_identity = commander.color_identity | bg.color_identity
            partners.append([cbg_name, cbg_color_identity, 'none'])

    
    friends_forever = commanders[commanders['partner'] == 'Friends forever'].sort_values(by=['name'])

    for commander in friends_forever.itertuples(index=True):
        for i in range(commander.Index+1, len(friends_forever)):
            commander_partner = friends_forever.iloc[i]
            partners_name = commander.name + ' ' + commander_partner['name']
            partners_color_identity = commander.color_identity |  commander_partner['color_identity']
            partners.append([partners_name, partners_color_identity, 'none'])

    #doctor_and_companion = []
    #doctor_companion = commanders[commanders['partner'] == 'Doctor\'s companion']
    #for commander in doctor_companion.itertuples(index=True):
    #    for i in range(commander['Index'], len(doctor_companion)):
    #        commander_partner = commanders.iloc[i]
    #        partners_name = commander['name'] + ' ' + commander_partner['name']
    #        partners_color_identity = commander['color_identity'] + commander_partner['color_identity']
    #        doctor_and_companion.append([partners_name, partners_color_identity, 'none'])


    partner_withs = commanders[(commanders['partner'] != 'none') &
                               (commanders['partner'] != 'Partner') & (commanders['partner'] != 'Background') &
                               (commanders['partner'] !='Friends forever') & (commanders['partner'] != 'Doctor\'s companion')].sort_values(by=['name'])
    
    for commander in partner_withs.itertuples(index=True):
        partner_name = commander.partner
        commander_partner = partner_withs[partner_withs['name'] == partner_name].iloc[0]
        partners_name = commander.name + ' ' + commander_partner['name']
        partners_color_identity = commander.color_identity | commander_partner['color_identity']

        # try to not have duplicates e.g. Faldan and Pako and Pako and Faldan
        if commander_partner['name'] + ' ' + commander.name in [p[0] for p in partners]:
            continue
        partners.append([partners_name, partners_color_identity, 'none'])

    return pandas.DataFrame(partners, columns=commanders.columns)
    

