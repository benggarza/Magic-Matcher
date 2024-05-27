from bs4 import BeautifulSoup
import pandas
import requests
from urllib.parse import quote
from unidecode import unidecode
import re
import time

CI_MAPPING = {'rakdos': {'B','R'}, 'golgari': {'B','G'}, 'selesnya':{'G','W'}, 'boros':{'R','W'}, 'dimir':{'U','B'},
               'azorius': {'W','U'}, 'orzhov':{'W','B'}, 'izzet':{'U','R'}, 'simic':{'U','G'}, 'gruul':{'R','G'},
               'jund':{'B','R','G'}, 'naya':{'R','G','W'}, 'bant':{'G','W','U'}, 'mardu':{'B','R','W'}, 
               'esper':{'B','W','U'}, 'jeskai':{'R','W','U'}, 'grixis':{'B','R','U'}, 'sultai':{'B','U','G'},
               'abzan':{'B','W','G'}, 'temur':{'G','R','U'}}

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
    if ci in CI_MAPPING.keys():
        ci_set = CI_MAPPING[ci]
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

def format_scryfall_string(s : str):
    # Kongming, "Sleeping Dragon"
    fs = re.sub('\"', '\'', s)
    fs = quote(fs, safe=' ')
    fs = re.sub('\s+', '+', fs)
    return fs

# score function for cards
# low sample sizes get reduced impact scores due to high variance
def get_score(num : int, potential : int, synergy : float, pdh : bool = False) -> float:
    #return 1 + (1-math.exp(-(num/potential)))/(1-math.exp(-1))
    #return 2-((num/potential)-1)**2
    if potential < 5:
        return 1 + ((num-0.5)/potential)**3 + max(0,synergy)**4
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