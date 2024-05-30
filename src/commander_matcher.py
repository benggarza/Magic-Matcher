import requests
import pandas as pd
import re
import time
import math
from unidecode import unidecode
from math import sqrt
import sys
from os import path
from utils import valid_ci, format_keys, get_score, insert, get_index_rank, get_ci_set
from requester import get_cardlist, get_commanders_from_scryfall, import_collection, import_commanders, import_pdh_commanders

def search_my_commanders(num_top : int = 10, score_threshold : float = 0, pdh : bool = False):
    # Grab list of commanders
    commander_df = pd.read_csv('data/collection/pdh_commanders.csv' if pdh else 'data/collection/commanders.csv')
    commander_names = commander_df['name']
    commander_keys = format_keys(commander_names)

    collection = pd.read_csv('data/collection/collection.csv',index_col=0)

    search_commanders(commander_keys, commander_names, collection, 'my', num_top=num_top, score_threshold=score_threshold, pdh=pdh)

def search_all_commanders(num_top : int = 10, depth : int = sys.maxsize, score_threshold : float = 0, start : int = 0, ci : str = None, pdh : bool = False):
    if ci is not None and not valid_ci(ci):
            print(f"Error: Invalid color identity {ci}")
            exit(1)

    collection_df = pd.read_csv('data/collection/collection.csv',index_col=0).drop_duplicates()
    #collection_names = collection_df['Name'].drop_duplicates().to_list()

    commanders = pd.DataFrame()
    try:
        commanders = pd.read_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv', converters={'color_identity': eval})
    except:
        print("Downloading commander list from scryfall...")
        commanders = get_commanders_from_scryfall(pdh=pdh)

    commanders_color = commanders
    if ci is not None:
        ci_set = get_ci_set(ci)
        commanders_color = commanders[commanders['color_identity'] == ci_set]

    commander_names = commanders_color['name']

    commander_names = commander_names.iloc[start:min(start+depth, len(commander_names))]

    commander_keys = format_keys(commander_names)

    search_commanders(commander_keys, commander_names, collection_df, ci if ci is not None else 'all', num_top=num_top, score_threshold=score_threshold, pdh=pdh)

# TODO: remove as many of these iterations as possible, replace with merges, vector operations
def search_commanders(commander_keys : pd.Series, commander_names : pd.Series, collection : pd.DataFrame, category_name : str,
                      num_top : int = 10, score_threshold : float = 0,
                      pdh : bool = False):
    
    commander_results = []

    skiplist = pd.read_csv('data/collection/skip.csv')#['name'].to_list()
    # For each commander...
    for i, (commander_name, commander_key) in enumerate(zip(commander_names, commander_keys)):
        # skip commanders in skiplist
        if commander_name in skiplist['name']:
            print(f"{commander_name} found in skiplist, skipping...")
            continue
        print(f"{i+1}/{len(commander_names)}: Evaluating {commander_name}")
        cardlist = get_cardlist(commander_key, pauper=pdh) 
        if cardlist is None:
            print(f'Error: {commander_name} ({commander_key}) did not return cardlist. Skipping..')
            continue

        cardlist['score'] = cardlist.apply(get_score, axis=1, pdh=pdh)

        in_collection = cardlist.merge(collection, on='oracle_id', how='inner')
        commander_score = in_collection['score'].sum()
        num_cards = len(in_collection)
        

        print(f"Score: {commander_score:3.3f}\tNum Cards: {num_cards:3d}")
        commander_results.append({'name':commander_name, 'score':commander_score,'num_cards':num_cards})

    commander_results_df = pd.DataFrame(commander_results, columns=['name','score','num_cards'])
    commander_results_df.sort_values(by=['score','num_cards'], axis=0, ascending=False, ignore_index=True, inplace=True)

    print()
    # Show the commanders with the top counts
    with open(f'reports/commanderlists/top_{category_name}_{"pdh_" if pdh else ""}commanders.txt','w') as f:
        print(category_name)
        print(f"Rank:\tCommander Name\t\t\t\t\t\t\t\tNum Cards\tScore")
        f.write(f"Rank:\tCommander Name \t\t\t\t\t\t\t\tNum Cards\tScore\n")
        for row in commander_results_df.itertuples(index=True):
            rank = row.Index
            if rank > num_top:
                break
            cname = row.name
            cscore = row.score
            cnum = row.num_cards
            print(f"{rank+1:2d}:\t{cname:70}\t{cnum:3d}\t\t{cscore:3.1f}")
            f.write(f"{rank+1:2d}:\t{cname:70}\t{cnum:3d}\t\t{cscore:3.1f}\n")

def get_commander_cardlist(commander_name : str, pdh : bool = False):
    commander_df = pd.read_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv')
    if commander_name not in commander_df['name'].to_list():
        print(f"Error: {commander_name} is an invalid commander name")
        exit(1)

    commander_key = format_keys(pd.Series([commander_name]))[0]

    collection = pd.read_csv('data/collection/collection.csv',index_col=0)

    rec_cardlist = get_cardlist(commander_key, pauper=pdh)
    rec_cardlist['score'] = rec_cardlist.apply(get_score, axis=1, pdh=pdh)

    in_collection = rec_cardlist.merge(collection, on='oracle_id', how='inner')
    commander_score = in_collection['score'].sum()
    num_cards = len(in_collection)

    with open(f'reports/cardlists/{commander_name}_{"pdh_" if pdh else ""}cardlist.txt', 'w') as f:
        f.write(f"{commander_name:80}\tscore: {commander_score:3.3f}\tnum cards: {num_cards:3d}\n\n")
        for card in in_collection.itertuples():
            f.write(f"{card.name:80}\t{card.score:3.0%}\n")

    return in_collection

def search_all_color_identities(num_top : int = sys.maxsize, pdh : bool = False):
    # test color identity filtering
    colors = ['w','u','b','r','g']
    color_pairs = ['rakdos','golgari','selesnya','boros','dimir','azorius','orzhov', 'izzet', 'simic','gruul']
    color_trios = ['jund', 'naya', 'bant', 'mardu', 'esper', 'jeskai', 'grixis', 'sultai', 'abzan', 'temur']
    # colorless commanders
    search_all_commanders(20, 2000, 0,ci='c', pdh=pdh)

    # monocolor
    for monocolor in colors:
        search_all_commanders(20, 2000, 0,ci=monocolor, pdh=pdh)
    # pair colors
    for color_pair in color_pairs:
        search_all_commanders(20, 2000, 0, ci=color_pair, pdh=pdh)
    # trios
    for color_trio in color_trios:
        search_all_commanders(20, 2000, 0, ci=color_trio, pdh=pdh)
    # 4 color
    for i in range(len(colors)):
        four_color = ''
        for j in range(i+1, len(colors)):
            four_color += colors[j]
        for j in range(0, i):
            four_color += colors[j]
        search_all_commanders(10, 2000, 0, ci=four_color, pdh=pdh)

    # search five color
    search_all_commanders(20, 2000, 0, ci='wubrg', pdh=pdh)

def init():
    if not path.exists('data/collection/collection.csv'):
        import_collection()
    if not path.exists('data/collection/commanders.csv'):
        import_commanders()
    if not path.exists('data/collection/pdh_commanders.csv'):
        import_pdh_commanders()

def main():
    init()
    print('before search all ci call')
    # start with a general top list
    #search_all_commanders(num_top=50,start=3547)
    #search_all_commanders(num_top=50,pdh=True, start=5290)
    # then search through each color identity
    #search_all_color_identities(num_top=50)
    search_all_commanders(num_top=20,ci='w')
    #search_all_color_identities(num_top=50, pdh=True)
    # THEN search through my commanders
    ##search_my_commanders(30)
    #search_my_commanders(30, pdh=True)

if __name__ == '__main__':
    main()
