import pandas
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
def get_score(num : int, potential : int) -> float:
    #return 1 + (1-math.exp(-(num/potential)))/(1-math.exp(-1))
    #return 2-((num/potential)-1)**2
    return 1 + (num/potential)**2

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
